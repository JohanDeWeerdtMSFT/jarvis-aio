"""goals onto the kernel spine (#1): goal lifecycle transitions publish canonical
JarvisEvents, and the goal→Plan shadow is credited in the coverage matrix.

A goal is an orchestration path — when it comes due it runs the headless agent,
whose tool-calls actuate through the already-wired paths. What `goals` itself
puts on the spine is its `goal.transition` events (parity: they enter the stream
and the ledger records them, no consumer reacts yet) and its goal-as-Plan shadow.
These tests cover the `from_goal` builder, `events.publish_goal`, and
`async_process_due` actually publishing on engage + close.
"""
from datetime import datetime

import pytest

from fakes import FakeHass

NOW = datetime(2026, 7, 12, 9, 0, 0)


# ── the pure builder ────────────────────────────────────────────────────────────

def test_from_goal_builder(load):
    K = load("kernel.event")
    ev = K.from_goal("closed", goal_id=7, title="Guest prep", status="done",
                     correlation_id="corr_3")
    assert ev.type == K.EVENT_GOAL
    assert ev.source == "goals"
    assert ev.subject == "7"                       # goal id, stringified
    assert ev.correlation_id == "corr_3"
    assert ev.data == {"action": "closed", "goal_id": 7,
                       "title": "Guest prep", "status": "done"}


# ── wiring a FakeHass to a real bus + collector ─────────────────────────────────

@pytest.fixture
def bus_hass(load):
    bus = load("kernel.event_bus").JarvisEventBus()
    captured = []
    bus.subscribe_all(lambda ev: captured.append(ev))
    hass = FakeHass()
    hass.data["jarvis"] = {"entry1": {"event_bus": bus}}
    return hass, bus, captured


def test_publish_goal_reaches_the_bus(load, bus_hass):
    events = load("events")
    hass, bus, captured = bus_hass
    events.publish_goal(hass, "engaged", goal_id=3, title="Warm the den",
                        status="active")
    assert len(captured) == 1
    ev = captured[0]
    assert ev.type == "goal.transition"
    assert ev.data["action"] == "engaged" and ev.data["status"] == "active"
    assert ev.data["goal_id"] == 3


def test_publish_goal_no_bus_is_silent(load):
    events = load("events")
    # No bus wired → best-effort no-op, never raises.
    events.publish_goal(FakeHass(), "closed", goal_id=1, status="failed")


# ── async_process_due publishes on engage + close ──────────────────────────────

@pytest.fixture
def quiet_db(load, monkeypatch):
    db = load("database")
    monkeypatch.setattr(db, "save_activity", lambda **kw: None)
    return db


def _mk(goals):
    return goals.create("Guest prep", "house ready for guests",
                        ["tidy living room"], now=NOW)


async def test_process_due_publishes_engaged_and_closed(load, tmp_path, monkeypatch,
                                                        bus_hass, quiet_db):
    goals = load("goals")
    monkeypatch.setattr(goals, "DB_PATH", str(tmp_path / "patterns.db"))
    hass, bus, captured = bus_hass
    gid = _mk(goals)["id"]

    async def runner(prompt, ctx):
        goals.update(gid, status="done", result="ready, sir.",
                     now=NOW, db_path=goals.DB_PATH)
        return "done"

    await goals.async_process_due(hass, {}, runner, now=NOW, db_path=goals.DB_PATH)
    goal_events = [e for e in captured if e.type == "goal.transition"]
    actions = [e.data["action"] for e in goal_events]
    assert "engaged" in actions and "closed" in actions
    closed = [e for e in goal_events if e.data["action"] == "closed"][-1]
    assert closed.data["status"] == "done" and closed.data["goal_id"] == gid


async def test_process_due_active_goal_emits_engaged_only(load, tmp_path, monkeypatch,
                                                         bus_hass, quiet_db):
    goals = load("goals")
    monkeypatch.setattr(goals, "DB_PATH", str(tmp_path / "patterns.db"))
    hass, bus, captured = bus_hass
    gid = _mk(goals)["id"]

    async def runner(prompt, ctx):
        goals.update(gid, progress_note="still working",
                     now=NOW, db_path=goals.DB_PATH)
        return "working"

    await goals.async_process_due(hass, {}, runner, now=NOW, db_path=goals.DB_PATH)
    actions = [e.data["action"] for e in captured if e.type == "goal.transition"]
    assert "engaged" in actions and "closed" not in actions   # quiet while working
