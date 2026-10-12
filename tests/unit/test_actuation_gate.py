"""Deterministic authorization gate at the actuator/service-dispatch boundary,
opt-in bootstrap defaults, and the retrieval -> control separation."""
import sys
import types

import pytest

from fakes import FakeHass

if "aiohttp" not in sys.modules:
    _aiohttp = types.ModuleType("aiohttp")
    _aiohttp.ClientTimeout = lambda **kw: None
    _aiohttp.ClientSession = object
    sys.modules["aiohttp"] = _aiohttp
if "homeassistant.helpers.aiohttp_client" not in sys.modules:
    _ac = types.ModuleType("homeassistant.helpers.aiohttp_client")
    _ac.async_get_clientsession = lambda hass: None
    sys.modules["homeassistant.helpers.aiohttp_client"] = _ac


@pytest.fixture
def gate(load):
    return load("actuation_gate")


@pytest.fixture
def cfg(load, monkeypatch):
    """Patch the JARVIS config accessor; returns the dict backing it."""
    store = {}
    jc = load("jarvis_config")
    monkeypatch.setattr(jc, "get", lambda k, d=None: store.get(k, d))
    return store


@pytest.fixture
def act(load, cfg):
    mod = load("actuation")
    mod._autonomous_budget = None
    mod._autonomous_loop = None
    mod._loop_detector = None
    mod._agency_budget = None
    return mod


def _call(gate, domain, service, entity, **extra):
    data = {"entity_id": entity, **extra}
    return gate.authorize(FakeHass(), domain, service, data)[0]


# ── direct-target bypass ─────────────────────────────────────────────────────

@pytest.mark.parametrize("domain,service,entity", [
    ("lock", "unlock", "lock.front_door"),
    ("lock", "open", "lock.front_door"),
    ("alarm_control_panel", "alarm_disarm", "alarm_control_panel.home"),
    ("cover", "open_cover", "cover.garage_door"),
    ("siren", "turn_on", "siren.hall"),
    ("camera", "turn_off", "camera.porch"),
    ("valve", "open_valve", "valve.water"),
])
def test_sensitive_services_denied_by_default(gate, cfg, domain, service, entity):
    assert _call(gate, domain, service, entity) is False


@pytest.mark.parametrize("bad", [
    "all", "light.a,light.b", ["light.a", "light.b"], "", None, "Light.A",
    "light.a ", "light.*", 5,
])
def test_non_single_entity_targets_denied(gate, cfg, bad):
    data = {"entity_id": bad}
    assert gate.authorize(FakeHass(), "light", "turn_on", data)[0] is False


@pytest.mark.parametrize("key", ["area_id", "device_id", "floor_id", "label_id", "target"])
def test_wider_target_keys_denied(gate, cfg, key):
    assert _call(gate, "light", "turn_on", "light.a", **{key: "x"}) is False


def test_domain_mismatch_denied(gate, cfg):
    assert _call(gate, "light", "turn_on", "lock.front_door") is False


def test_unknown_domain_and_service_denied(gate, cfg):
    assert _call(gate, "shell_command", "run", "shell_command.x") is False
    assert _call(gate, "light", "reload", "light.a") is False


def test_malformed_input_denied(gate, cfg):
    assert gate.authorize(FakeHass(), None, "turn_on", {"entity_id": "light.a"})[0] is False
    assert gate.authorize(FakeHass(), "light", "turn_on", None)[0] is False


def test_low_impact_and_securing_actions_allowed(gate, cfg):
    assert _call(gate, "light", "turn_on", "light.kitchen")
    assert _call(gate, "lock", "lock", "lock.front_door")
    assert _call(gate, "cover", "close_cover", "cover.garage_door")
    assert _call(gate, "alarm_control_panel", "alarm_arm_away", "alarm_control_panel.home")


def test_blind_cover_may_open_but_garage_may_not(gate, cfg):
    hass = FakeHass()
    hass.states.set("cover.blind", "closed", device_class="blind")
    hass.states.set("cover.garage", "closed", device_class="garage")
    assert gate.authorize(hass, "cover", "open_cover", {"entity_id": "cover.blind"})[0]
    assert not gate.authorize(hass, "cover", "open_cover", {"entity_id": "cover.garage"})[0]
    assert not gate.authorize(hass, "cover", "open_cover", {"entity_id": "cover.unknown"})[0]


# ── scripts / scenes / automations ───────────────────────────────────────────

@pytest.mark.parametrize("domain,service,entity", [
    ("script", "turn_on", "script.anything"),
    ("scene", "turn_on", "scene.movie"),
    ("automation", "trigger", "automation.morning"),
])
def test_script_scene_automation_denied_by_default(gate, cfg, domain, service, entity):
    assert _call(gate, domain, service, entity) is False


def test_allowlist_is_exact_per_entity(gate, cfg):
    cfg["actuation_allowlist"] = ["script.goodnight"]
    assert _call(gate, "script", "turn_on", "script.goodnight") is True
    assert _call(gate, "script", "turn_on", "script.other") is False
    assert _call(gate, "lock", "unlock", "lock.goodnight") is False


@pytest.mark.parametrize("bad", [
    "script.goodnight",            # not a list
    ["script.*"],                  # wildcard
    ["*"],
    ["script.goodnight", 5],       # mixed types
    ["Script.Goodnight"],
    {"script.goodnight": True},
])
def test_malformed_allowlist_fails_closed(gate, cfg, bad):
    cfg["actuation_allowlist"] = bad
    assert gate.allowlist() == frozenset()
    assert _call(gate, "script", "turn_on", "script.goodnight") is False


# ── dispatch boundary: aliases / area resolution / plans ─────────────────────

async def test_execute_actuator_blocks_before_service_call(act, cfg):
    hass = FakeHass()
    hass.states.set("lock.front_door", "locked")
    ok, detail = await act.execute_actuator(
        hass, capability="lock.unlock", entity_id="lock.front_door",
        domain="lock", service="unlock", data={"entity_id": "lock.front_door"},
        action="unlock")
    assert ok is False
    assert "authorization" in detail
    assert hass.service_calls == []


async def test_execute_actuator_allows_allowlisted_entity(act, cfg):
    cfg["actuation_allowlist"] = ["script.goodnight"]
    hass = FakeHass()
    hass.states.set("script.goodnight", "off")
    ok, _ = await act.execute_actuator(
        hass, capability="script.turn_on", entity_id="script.goodnight",
        domain="script", service="turn_on",
        data={"entity_id": "script.goodnight"}, action="run")
    assert ok is True
    assert any(c[0] == "script" for c in hass.service_calls)


async def test_guarded_call_raises_and_never_dispatches(act, cfg):
    hass = FakeHass()
    with pytest.raises(PermissionError):
        await act.guarded_call(hass, "lock", "unlock", {"entity_id": "lock.front_door"})
    assert hass.service_calls == []


async def test_resolved_alias_or_area_member_is_still_gated(act, cfg):
    # Whatever resolution (alias, area expansion) produced the entity id, the
    # final call is authorized on the concrete id, so a sensitive member of an
    # area is denied while a light in the same area is allowed.
    hass = FakeHass()
    hass.states.set("lock.back_door", "locked")
    hass.states.set("light.hall", "off")
    denied, _ = await act.execute_actuator(
        hass, capability="lock.unlock", entity_id="lock.back_door",
        domain="lock", service="unlock", data={"entity_id": "lock.back_door"},
        action="unlock")
    allowed, _ = await act.execute_actuator(
        hass, capability="light.turn_on", entity_id="light.hall",
        domain="light", service="turn_on", data={"entity_id": "light.hall"},
        action="on")
    assert denied is False and allowed is True


async def test_safety_path_denies_unauthorized_but_secures(act, cfg):
    hass = FakeHass()
    hass.states.set("lock.front", "unlocked")
    hass.states.set("lock.front2", "locked")
    ok = await act.execute_safety_actuator(
        hass, capability="lock.unlock", entity_id="lock.front2",
        domain="lock", service="unlock", data={"entity_id": "lock.front2"},
        action="unlock")
    assert ok is False
    assert hass.service_calls == []
    ok = await act.execute_safety_actuator(
        hass, capability="lock.lock", entity_id="lock.front",
        domain="lock", service="lock", data={"entity_id": "lock.front"},
        action="lock")
    await hass.drain()
    assert ok is True


# ── HA Assist API tool fallback ──────────────────────────────────────────────

def test_ha_api_tools_denied_unless_read_only_or_allowlisted(gate, cfg):
    assert gate.ha_tool_permitted("HassGetState")
    assert not gate.ha_tool_permitted("HassTurnOn")
    assert not gate.ha_tool_permitted("HassLightSet")
    assert not gate.ha_tool_permitted(None)
    cfg["ha_api_tool_allowlist"] = ["HassLightSet"]
    assert gate.ha_tool_permitted("HassLightSet")
    assert not gate.ha_tool_permitted("HassTurnOn")
    cfg["ha_api_tool_allowlist"] = "HassTurnOn"
    assert not gate.ha_tool_permitted("HassTurnOn")


async def test_execute_tool_ha_fallback_blocked(load, cfg):
    agent = load("agent")

    class Api:
        called = False

        async def async_call_tool(self, call):
            Api.called = True
            return {}

    out = await agent._execute_tool(FakeHass(), "HassTurnOn", {"name": "x"}, Api(), "hi")
    assert Api.called is False
    assert "error" in out.lower() or "not" in out.lower()


# ── search-returned instructions cannot drive an action ──────────────────────

def test_untrusted_sources_are_read_only_classified(load):
    agent = load("agent")
    for name in agent._UNTRUSTED_OUTPUT_TOOLS - {"delegate_task"}:
        assert agent._is_read_only_tool(name), name
    for name in ("control_device", "execute_plan", "bulk_control",
                 "run_scene_script", "HassTurnOn", "some_new_tool"):
        assert not agent._is_read_only_tool(name), name


async def test_tainted_loop_refuses_control_tools(load, cfg):
    agent = load("agent")
    hass = FakeHass()
    hass.states.set("lock.front_door", "locked")
    out = await agent._execute_tool(
        hass, "control_device",
        {"entity": "lock.front_door", "action": "unlock"}, None, "x",
        untrusted_context=True)
    assert "refused" in out
    assert hass.service_calls == []


async def test_tainted_loop_still_allows_read_only_tools(load, cfg):
    agent = load("agent")
    hass = FakeHass()
    hass.states.set("light.a", "on")
    out = await agent._execute_tool(
        hass, "get_entity_state", {"entity_id": "light.a"}, None, "x",
        untrusted_context=True)
    assert "refused" not in out


# ── startup defaults ─────────────────────────────────────────────────────────

def test_bootstrap_flags_default_off(load, cfg):
    bs = load("bootstrap")
    assert bs.is_opted_in("auto_bootstrap") is False
    assert bs.is_opted_in("auto_pipeline") is False


@pytest.mark.parametrize("val", ["true", 1, "yes", None, [True]])
def test_bootstrap_opt_in_requires_real_boolean(load, cfg, val):
    bs = load("bootstrap")
    cfg["auto_bootstrap"] = val
    assert bs.is_opted_in("auto_bootstrap") is False
    cfg["auto_bootstrap"] = True
    assert bs.is_opted_in("auto_bootstrap") is True


async def test_pipeline_repair_does_nothing_by_default(load, cfg):
    bs = load("bootstrap")
    hass = FakeHass()
    res = await bs.async_ensure_pipeline_agent(hass)
    assert not res
    assert hass.service_calls == []


async def test_default_startup_never_runs_bootstrap(load, cfg, monkeypatch):
    bs = load("bootstrap")
    ran = []

    async def fake_run(*a, **k):
        ran.append(1)

    monkeypatch.setattr(bs, "async_run_bootstrap", fake_run)
    monkeypatch.setattr(bs, "is_supervised", lambda: True)
    tasks = []
    hass = types.SimpleNamespace(
        is_running=True,
        async_create_background_task=lambda coro, name: tasks.append(coro))
    bs.schedule_bootstrap(hass)
    for coro in tasks:
        await coro
    assert tasks and ran == []
