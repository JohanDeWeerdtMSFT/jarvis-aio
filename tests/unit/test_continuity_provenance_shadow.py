"""Provenance shadow extension (#237, 9.3.0): when continuity reads the open
situations for its continuity view, it also packages each as a
kernel.provenance.Provenance and logs the authoritative one — observe-only,
extending the fabric's coverage to the *situation* domain. The continuity read
returns the same rows whether this runs or not, and it never raises.
"""
import logging
import types

import pytest


@pytest.fixture
def cont(load):
    return load("continuity")


def _sit(kind, subject=None, updated_ts=1000.0, state="active", sid="s1"):
    return types.SimpleNamespace(kind=kind, subject=subject, updated_ts=updated_ts,
                                 state=state, id=sid)


def test_emit_logs_provenance_for_open_situations(cont, caplog):
    sits = [_sit("delivery", "front_door", 1000.0),
            _sit("freeze", None, 2000.0)]
    with caplog.at_level(logging.DEBUG):
        cont._emit_situation_provenance_shadow(sits)
    msgs = [r.getMessage() for r in caplog.records]
    assert any("provenance(shadow)" in m and "open-situation" in m for m in msgs)


def test_emit_kill_switch_silences(cont, caplog, monkeypatch):
    monkeypatch.setattr(cont, "PROVENANCE_SHADOW", False)
    with caplog.at_level(logging.DEBUG):
        cont._emit_situation_provenance_shadow([_sit("delivery", "x")])
    assert not any("provenance(shadow)" in r.getMessage() for r in caplog.records)


def test_emit_empty_is_noop(cont, caplog):
    with caplog.at_level(logging.DEBUG):
        cont._emit_situation_provenance_shadow([])
    assert not any("provenance(shadow)" in r.getMessage() for r in caplog.records)


def test_emit_never_raises_on_bad_situations(cont):
    # objects missing attributes must not raise (getattr defaults cover it)
    cont._emit_situation_provenance_shadow([object(), _sit("ok", "y")])


def test_live_situations_returns_rows_and_invokes_emit(cont, monkeypatch):
    seen = {}
    monkeypatch.setattr(cont, "_emit_situation_provenance_shadow",
                        lambda sits: seen.setdefault("n", len(sits)))

    class _Store:
        def __init__(self, *a, **k):
            pass

        def open_situations(self):
            return [_sit("delivery", "door", 1.0, "active", "a"),
                    _sit("freeze", None, 2.0, "active", "b")]

    import jc.kernel.situation as sm
    monkeypatch.setattr(sm, "SituationManager", _Store)
    monkeypatch.setattr(cont, "config_path_str", lambda *a, **k: "/tmp/jarvis-x.db")

    rows = cont._live_situations(hass=None)
    assert len(rows) == 2                         # rows unchanged by the shadow emit
    assert rows[0]["label"].startswith("delivery")
    assert rows[0]["status"] == "active"
    assert seen.get("n") == 2                     # emit was handed the situations
