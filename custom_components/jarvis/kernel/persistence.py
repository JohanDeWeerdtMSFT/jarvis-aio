"""Unified SQLite access seam (kernel Phase 0, docs/KERNEL_PLAN.md).

Today stores open connections several different ways — some with
``sqlite3.connect(path, factory=ClosingConnection)`` and a timeout, others with a
bare ``sqlite3.connect(path)`` that never sets a busy-timeout and relies on GC to
close. This module is the one canonical opener plus a home for schema migrations,
so every store can converge on a single pattern over time.

**No schema merge** (explicitly out of scope per the plan): each store keeps its
own database file and its own tables. This seam only removes the drift in *how*
connections are opened, and sequences/records migrations so they run exactly once.

Pure-ish: imports only stdlib and the integration's own ``sqlite_utils``; no Home
Assistant import, so it is unit-testable without HA.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Callable, Iterator, Sequence

try:  # normal runtime: real nested package (custom_components.jarvis.kernel)
    from ..sqlite_utils import ClosingConnection
except (ImportError, ValueError):
    # The flat unit-test harness execs this file outside its package, so the
    # relative import can't resolve. Load the sibling module by path instead.
    import importlib.util as _ilu
    from pathlib import Path as _Path

    _spec = _ilu.spec_from_file_location(
        "jarvis_sqlite_utils",
        _Path(__file__).resolve().parent.parent / "sqlite_utils.py",
    )
    _su = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_su)  # type: ignore[union-attr]
    ClosingConnection = _su.ClosingConnection

_LOGGER = logging.getLogger(__name__)

# A non-zero busy-timeout so concurrent writers wait briefly instead of raising
# "database is locked"; matches the longest timeout already used in the codebase.
DEFAULT_TIMEOUT = 10.0

# Migration = fn(conn) -> None. Its 1-based position in the list is its version.
Migration = Callable[[sqlite3.Connection], None]

_VERSION_TABLE = "_kernel_schema_version"


def connect(db_path, *, timeout: float = DEFAULT_TIMEOUT) -> sqlite3.Connection:
    """Open a SQLite connection the one canonical way.

    Uses the ``ClosingConnection`` factory (deterministic close when used as a
    context manager) and a sane busy-timeout. Callers may use it directly or as
    ``with connect(path) as conn:`` — the latter commits/rolls back and closes.
    """
    return sqlite3.connect(str(db_path), timeout=timeout, factory=ClosingConnection)


@contextmanager
def transaction(db_path, *, timeout: float = DEFAULT_TIMEOUT) -> Iterator[sqlite3.Connection]:
    """Yield a connection wrapped in a single explicit transaction.

    Commits on clean exit, rolls back on exception, and always closes. The
    transaction is driven manually (autocommit off + an explicit ``BEGIN``) so a
    rollback also undoes schema changes (``CREATE TABLE`` …) — Python's legacy
    sqlite3 mode implicitly commits DDL before a deferred transaction, which would
    otherwise leave a half-applied migration behind on Python < 3.12.
    """
    conn = connect(db_path, timeout=timeout)
    conn.isolation_level = None  # manual control; no implicit BEGIN/COMMIT
    try:
        conn.execute("BEGIN")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def schema_version(db_path, *, timeout: float = DEFAULT_TIMEOUT) -> int:
    """Current recorded schema version for ``db_path`` (0 if never migrated)."""
    conn = connect(db_path, timeout=timeout)
    try:
        try:
            row = conn.execute(
                f"SELECT version FROM {_VERSION_TABLE} WHERE id = 1").fetchone()
        except sqlite3.OperationalError:
            return 0  # table doesn't exist yet
        return int(row[0]) if row else 0
    finally:
        conn.close()


# Substrings SQLite uses for an unreadable / corrupt / non-database file. Matched
# strictly so ONLY real file corruption triggers recovery — a migration's own SQL
# error (a different DatabaseError / OperationalError) must re-raise untouched, so
# a healthy database is never quarantined and its data never discarded.
_CORRUPTION_MARKERS = (
    "malformed",                       # database disk image is malformed
    "file is not a database",
    "is not a database",
    "file is encrypted or is not a database",
    "disk image is malformed",
)


def _is_corruption(exc: BaseException) -> bool:
    """True only for a SQLite error that means the file itself is unreadable."""
    if not isinstance(exc, sqlite3.DatabaseError):
        return False
    msg = str(exc).lower()
    return any(m in msg for m in _CORRUPTION_MARKERS)


def _quarantine_corrupt(db_path) -> str:
    """Move a corrupt DB (and its -wal/-shm sidecars) aside so a fresh one can be
    created, keeping the bad file for forensics. Returns the quarantine base path.
    Never raises — if a rename fails, the file is removed so recovery can proceed."""
    base = str(db_path)
    dest = f"{base}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}"
    for suffix in ("", "-wal", "-shm"):
        src = base + suffix
        if not os.path.exists(src):
            continue
        try:
            os.replace(src, dest + suffix)
        except OSError:
            try:
                os.remove(src)
            except OSError:
                pass
    return dest


def run_migrations(
    db_path,
    migrations: Sequence[Migration],
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> int:
    """Apply any not-yet-applied migrations in order, exactly once each.

    The applied version is tracked in a tiny ``_kernel_schema_version`` table, so
    re-running is idempotent (only migrations past the recorded version run).
    Returns the number applied this call. Everything runs in one transaction, so
    a failing migration rolls the whole batch back and leaves the version intact.

    **Corruption self-heal (HAOS fail-safe):** if the database file is corrupt —
    e.g. truncated by a power loss, the classic SQLite "database disk image is
    malformed" — the first access raises, which would otherwise break the store's
    setup. Here that one specific case is caught: the bad file is quarantined aside
    (kept for forensics) and the schema is rebuilt from the migrations, so the
    store comes back empty-but-working rather than dead. A migration's own SQL
    error is NOT corruption and re-raises untouched, so a healthy database is never
    discarded.
    """
    try:
        return _run_migrations_once(db_path, migrations, timeout=timeout)
    except sqlite3.DatabaseError as exc:
        if not _is_corruption(exc):
            raise
        quarantined = _quarantine_corrupt(db_path)
        _LOGGER.error(
            "kernel.persistence: %s is corrupt (%s) — quarantined to %s and "
            "rebuilding the schema empty", db_path, exc, quarantined)
        return _run_migrations_once(db_path, migrations, timeout=timeout)


def _run_migrations_once(
    db_path,
    migrations: Sequence[Migration],
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> int:
    applied = 0
    with transaction(db_path, timeout=timeout) as conn:
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {_VERSION_TABLE} "
            "(id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL)")
        row = conn.execute(
            f"SELECT version FROM {_VERSION_TABLE} WHERE id = 1").fetchone()
        current = int(row[0]) if row else 0

        for version, migration in enumerate(migrations, start=1):
            if version <= current:
                continue
            migration(conn)
            applied += 1

        new_version = max(current, len(migrations))
        if new_version != current:
            conn.execute(
                f"INSERT INTO {_VERSION_TABLE} (id, version) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET version = excluded.version",
                (new_version,))
    if applied:
        _LOGGER.debug("kernel.persistence: applied %d migration(s) to %s",
                      applied, db_path)
    return applied
