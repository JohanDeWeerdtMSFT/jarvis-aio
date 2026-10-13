"""jarvis.speak area resolution — id / name / alias / slug tolerance (issue #77)."""
import sys
import types

import pytest
from fakes import FakeHass


class _Area:
    def __init__(self, id, name, aliases=()):
        self.id = id
        self.name = name
        self.aliases = set(aliases)


def _norm(s):  # faithful to HA: casefold + collapse whitespace
    return " ".join(str(s or "").casefold().split())


class _AreaReg:
    def __init__(self, areas):
        self._areas = areas
        self._by_id = {a.id: a for a in areas}

    def async_get_area(self, area_id):
        return self._by_id.get(area_id)

    def async_get_area_by_name(self, name):  # HA matches the canonical name only
        n = _norm(name)
        return next((a for a in self._areas if _norm(a.name) == n), None)

    def async_list_areas(self):
        return list(self._areas)


@pytest.fixture
def pa(load, monkeypatch):
    areas = [
        _Area("01HULID", "Office"),                       # name only, id is a ULID
        _Area("lr", "Living Room", aliases={"Lounge"}),   # has an alias
        _Area("study_id", "Study", aliases={"Home Office"}),
    ]
    helpers = sys.modules.setdefault(
        "homeassistant.helpers", types.ModuleType("homeassistant.helpers"))
    ar = types.ModuleType("homeassistant.helpers.area_registry")
    ar.async_get = lambda hass: _AreaReg(areas)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.area_registry", ar)
    monkeypatch.setattr(helpers, "area_registry", ar, raising=False)
    # proactive_audio also imports config_validation and helpers.event at module
    # level; the core harness doesn't stub those, so supply minimal fakes.
    cv = types.ModuleType("homeassistant.helpers.config_validation")
    cv.string, cv.boolean = str, bool
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.config_validation", cv)
    monkeypatch.setattr(helpers, "config_validation", cv, raising=False)
    ev = types.ModuleType("homeassistant.helpers.event")
    ev.async_call_later = lambda *a, **k: (lambda: None)
    ev.async_track_time_interval = lambda *a, **k: (lambda: None)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.event", ev)
    monkeypatch.setattr(helpers, "event", ev, raising=False)
    if "homeassistant.exceptions" not in sys.modules:
        exc = types.ModuleType("homeassistant.exceptions")
        class HomeAssistantError(Exception): ...
        exc.HomeAssistantError = HomeAssistantError
        monkeypatch.setitem(sys.modules, "homeassistant.exceptions", exc)
    return load("proactive_audio")


def test_exact_area_id(pa):
    assert pa._resolve_area_id(None, "01HULID") == "01HULID"


def test_canonical_name_case_insensitive(pa):
    # "office" resolves to the area named "Office" via HA's own name matcher.
    assert pa._resolve_area_id(None, "office") == "01HULID"


def test_alias_resolves(pa):
    # "home office" is an alias of "Study" — HA's name matcher misses it, the
    # slug/alias fallback catches it (issue #77).
    assert pa._resolve_area_id(None, "home office") == "study_id"
    assert pa._resolve_area_id(None, "lounge") == "lr"


def test_underscore_and_spacing_variants(pa):
    assert pa._resolve_area_id(None, "living_room") == "lr"
    assert pa._resolve_area_id(None, "Living   Room") == "lr"


def test_unknown_area_returns_none(pa):
    assert pa._resolve_area_id(None, "garage") is None
    assert pa._resolve_area_id(None, "") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entity_id", "expected_calls"),
    [
        ("media_player.office_speaker", 2),
        ("media_player.office_speaker\n", 0),
    ],
)
async def test_announce_volume_dispatch_uses_resolved_speakers_and_actuator_gate(
    pa, monkeypatch, entity_id, expected_calls,
):
    hass = FakeHass()
    hass.states.set(entity_id, "idle", volume_level=0.35)
    monkeypatch.setattr(pa.audio_routing, "entity_area", lambda _h, _e: "01HULID")
    _inject_jarvis_config(monkeypatch, "")
    entity_filter = types.ModuleType("jc.entity_filter")
    entity_filter.is_excluded = lambda _h, _e: False
    monkeypatch.setitem(sys.modules, "jc.entity_filter", entity_filter)
    monkeypatch.setattr(
        pa, "_build_telemetry",
        lambda *_args: {"media_active": False},
    )
    monkeypatch.setattr(
        pa._PROSODY, "calculate_vocal_profile",
        lambda _telemetry: {
            "volume": 0.7, "speech_rate": 1.0, "style": "test",
            "duck_media": True,
        },
    )
    monkeypatch.setattr(pa, "_proximity_enabled", lambda: False)

    async def no_speech(*_args, **_kwargs):
        return None

    async def no_sleep(*_args, **_kwargs):
        return None

    monkeypatch.setattr(pa, "_speak_tts", no_speech)
    monkeypatch.setattr(pa.asyncio, "sleep", no_sleep)

    await pa._announce(hass, "Test announcement", "01HULID", False)

    assert [call[:2] for call in hass.service_calls] == (
        [("media_player", "volume_set")] * expected_calls
    )
    if expected_calls:
        assert all(call[2]["entity_id"] == entity_id for call in hass.service_calls)


def test_known_area_labels_for_diagnostics(pa):
    assert pa._known_area_labels(None) == ["Living Room", "Office", "Study"]


# ── infra-audit target + broadcast (8.19.0) ──────────────────────────────────

def _inject_jarvis_config(monkeypatch, value):
    cfg = types.ModuleType("jc.jarvis_config")
    cfg.get = lambda key, default=None: value if value is not None else default
    monkeypatch.setitem(sys.modules, "jc.jarvis_config", cfg)


def test_audit_speak_target_uses_configured_area(pa, monkeypatch):
    _inject_jarvis_config(monkeypatch, "office")  # resolves to the Office area
    assert pa._audit_speak_target(None) == {"target_area": "office"}


def test_audit_speak_target_unset_broadcasts(pa, monkeypatch):
    _inject_jarvis_config(monkeypatch, "")  # no fixed area configured
    assert pa._audit_speak_target(None) == {"target_area": "", "broadcast": True}


def test_audit_speak_target_unresolvable_area_broadcasts(pa, monkeypatch):
    _inject_jarvis_config(monkeypatch, "nonexistent")  # not a real area
    assert pa._audit_speak_target(None) == {"target_area": "", "broadcast": True}


def test_dispatch_speak_broadcast_skips_area_resolution(pa, monkeypatch):
    import asyncio
    seen = {}

    async def _fake_announce(hass, message, area_id, critical):
        seen["area_id"] = area_id
        seen["message"] = message

    monkeypatch.setattr(pa, "_announce", _fake_announce)
    asyncio.run(pa._dispatch_speak(
        None, {"message": "infra alert", "target_area": "", "broadcast": True}))
    # Broadcast path announces with an empty area id (→ house broadcast set),
    # never dropping the alert for a missing area.
    assert seen == {"area_id": "", "message": "infra alert"}


def test_dispatch_speak_unknown_area_still_drops_without_broadcast(pa, monkeypatch):
    import asyncio
    called = {"n": 0}

    async def _fake_announce(hass, message, area_id, critical):
        called["n"] += 1

    monkeypatch.setattr(pa, "_announce", _fake_announce)
    asyncio.run(pa._dispatch_speak(
        None, {"message": "x", "target_area": "nonexistent"}))
    # Strict semantics preserved for normal callers: unknown area → dropped.
    assert called["n"] == 0


# ── infra-audit announce policy (8.21.0): no nagging, criticals only ──────────

def _verdict(critical, tags=("root storage",), alert=True):
    return {"alert_required": alert, "critical": critical,
            "message": "m", "tags": list(tags)}


def test_warning_is_not_spoken_by_default(pa):
    announce, sig = pa._infra_announce_decision(
        _verdict(False), speak_warnings=False,
        last_sig=None, last_ts=0.0, now=100.0, cooldown_s=3600.0)
    assert announce is False and sig[0] == "warn"


def test_warning_spoken_when_opted_in(pa):
    announce, _ = pa._infra_announce_decision(
        _verdict(False), speak_warnings=True,
        last_sig=None, last_ts=0.0, now=100.0, cooldown_s=3600.0)
    assert announce is True


def test_critical_spoken_first_time(pa):
    announce, sig = pa._infra_announce_decision(
        _verdict(True), speak_warnings=False,
        last_sig=None, last_ts=0.0, now=100.0, cooldown_s=3600.0)
    assert announce is True and sig[0] == "critical"


def test_same_critical_not_repeated_within_cooldown(pa):
    sig = ("critical", ("root storage",))
    announce, _ = pa._infra_announce_decision(
        _verdict(True), speak_warnings=False,
        last_sig=sig, last_ts=100.0, now=100.0 + 60, cooldown_s=3600.0)
    assert announce is False


def test_same_critical_repeats_after_cooldown(pa):
    sig = ("critical", ("root storage",))
    announce, _ = pa._infra_announce_decision(
        _verdict(True), speak_warnings=False,
        last_sig=sig, last_ts=100.0, now=100.0 + 3601, cooldown_s=3600.0)
    assert announce is True


def test_escalation_from_warning_to_critical_speaks_immediately(pa):
    # Last spoken was a warning (only possible with speak_warnings), now critical
    # on the same tags → must break through the cooldown.
    announce, _ = pa._infra_announce_decision(
        _verdict(True), speak_warnings=False,
        last_sig=("warn", ("root storage",)), last_ts=100.0,
        now=100.0 + 60, cooldown_s=3600.0)
    assert announce is True


def test_different_finding_set_speaks(pa):
    announce, _ = pa._infra_announce_decision(
        _verdict(True, tags=("system memory",)), speak_warnings=False,
        last_sig=("critical", ("root storage",)), last_ts=100.0,
        now=100.0 + 60, cooldown_s=3600.0)
    assert announce is True
