"""Notification delivery must be confirmed before it suppresses home audio."""
import pytest


@pytest.fixture
def routing(load, monkeypatch):
    cc = load("cognitive_core")
    driving = load("driving_mode")
    tts = load("tts_helper")
    audio = load("audio_routing")
    sleep = load("sleep_detection")
    config = load("jarvis_config")
    announced = []

    monkeypatch.setattr(driving, "should_route", lambda *args: False)
    monkeypatch.setattr(driving, "suppress_home_audio", lambda *args: True)
    monkeypatch.setattr(sleep, "_in_quiet_hours", lambda *args: False)
    monkeypatch.setattr(tts, "resolve_tts_for_context", lambda *args: "tts.example")
    monkeypatch.setattr(audio, "observer_speak_target",
                        lambda *args, **kwargs: (["media_player.kitchen"], "test"))
    monkeypatch.setattr(config, "get", lambda key, default=None: default)

    async def announce(*args, **kwargs):
        announced.append((args, kwargs))
    monkeypatch.setattr(tts, "async_announce", announce)
    return cc, driving, announced


@pytest.mark.parametrize(
    ("route", "sleeping", "result", "should_announce"),
    [
        ("driving", False, {"ok": True}, False),
        ("driving", False, {"ok": False, "error": "denied"}, True),
        ("quiet-hours", True, {"ok": True}, False),
        ("quiet-hours", True, {"ok": False, "error": "unavailable"}, True),
        ("driving", False, RuntimeError("handler failed"), True),
    ],
)
async def test_push_suppresses_audio_only_after_confirmed_delivery(
        routing, fake_hass, monkeypatch, route, sleeping, result, should_announce,
):
    cc, driving, announced = routing
    monkeypatch.setattr(driving, "should_route", lambda *args: route == "driving")
    attempts = []

    async def send(*args):
        attempts.append(args)
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(cc, "_push_notification", send)

    await cc._emit_action(
        fake_hass, {},
        {"type": "test_alert", "message": "Example alert", "urgency": "medium"},
        sleeping=sleeping,
    )

    assert len(attempts) == 1
    assert bool(announced) is should_announce
