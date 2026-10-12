"""Exact output endpoint policy, exercised through real configurable routes."""
import ast
import logging
from pathlib import Path
import sys
import types

import pytest


@pytest.fixture
def policy(load, monkeypatch):
    values = {}
    monkeypatch.setattr(load("actuation_gate"), "_cfg",
                        lambda key, default=None: values.get(key, default))
    return values


@pytest.fixture
def ha_error(monkeypatch):
    module = types.ModuleType("homeassistant.exceptions")
    module.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "homeassistant.exceptions", module)
    return module.HomeAssistantError


async def _value(value=None):
    return value


@pytest.fixture(params=["cognitive", "observer", "briefing", "sentinel", "appliance", "diagnostic"])
def notify_route(request, load, fake_hass, monkeypatch, ha_error):
    route = request.param
    if route == "cognitive":
        module = load("cognitive_core")
        return lambda svc: module._push_notification(
            fake_hass, {"notify_service": svc}, "Example alert", "arrival")
    if route == "observer":
        module = load("observer")
        module._STATE.hass = fake_hass
        fake_hass.data["jarvis"] = {"example": {"runtime_config": {}}}

        async def invoke(svc):
            module._STATE.config = {"notify_service": svc}
            fake_hass.data["jarvis"]["example"]["runtime_config"]["notify_service"] = svc
            return await module._send_notification("Example alert", urgency="high")
        return invoke
    if route == "briefing":
        module = load("proactive_briefing")
        return lambda svc: module._push_to_phone(
            fake_hass, {"notify_service": svc}, "Example alert", "arrival")
    if route == "sentinel":
        events = types.ModuleType("homeassistant.helpers.event")
        events.async_track_state_change_event = lambda *a, **kw: lambda: None
        events.async_track_time_interval = lambda *a, **kw: lambda: None
        monkeypatch.setitem(sys.modules, "homeassistant.helpers.event", events)
        module = load("sentinel")
        instance = module.JarvisSentinel(fake_hass, None, "friend")
        monkeypatch.setattr(instance, "_localize", lambda text: _value(text))
        monkeypatch.setattr(instance, "_tts_entity", lambda: None)
        monkeypatch.setattr(instance, "_speakers", lambda: [])
        monkeypatch.setattr(module, "async_announce", lambda *a, **kw: _value())
        monkeypatch.setattr(fake_hass, "async_add_executor_job", lambda *a: _value())
        monkeypatch.setattr(load("entity_filter"), "is_excluded", lambda *a: False)
        monkeypatch.setattr(sys.modules["jc"], "entity_filter", load("entity_filter"), raising=False)

        async def invoke(svc):
            monkeypatch.setattr(module.jarvis_config, "runtime_get",
                                lambda h, e, k, d=None: svc if k == "notify_service" else d)
            return await instance._announce_rule("binary_sensor.example",
                                                {"id": "example", "message": "Example alert"}, 1)
        return invoke
    if route == "appliance":
        module = load("appliance_monitor")
        monkeypatch.setattr(module, "_MON", module._MonitorState())
        module._MON.hass = fake_hass
        gate = load("output_gate")
        monkeypatch.setattr(sys.modules["jc"], "output_gate", gate, raising=False)
        monkeypatch.setattr(gate, "async_reserve_announcement",
                            lambda *a, **kw: _value((True, "allowed", "example")))
        monkeypatch.setattr(gate, "async_record_announcement", lambda *a, **kw: _value())
        monkeypatch.setattr(load("entity_filter"), "is_excluded", lambda *a: False)
        monkeypatch.setattr(sys.modules["jc"], "entity_filter", load("entity_filter"), raising=False)
        monkeypatch.setattr(load("audio_routing"), "observer_speak_target",
                            lambda *a, **kw: ([], "notify_only"))
        monkeypatch.setattr(load("sleep_detection"), "is_sleeping",
                            lambda *a, **kw: (False, "awake"))
        monkeypatch.setattr(sys.modules["jc"], "sleep_detection", load("sleep_detection"), raising=False)
        sensor = module._SensorState(
            "sensor.example_power", "Example Washer", module.ApplianceType.WASHER,
            discovery_method="explicit_config")

        async def invoke(svc):
            module._MON.config = {"notify_service": svc}
            return await module._announce_done(sensor, "washer")
        return invoke

    # Execute the actual registered handler body without bootstrapping an HA entry.
    path = Path(__file__).resolve().parents[2] / "custom_components" / "jarvis" / "__init__.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    handler = next(node for node in ast.walk(tree)
                   if isinstance(node, ast.AsyncFunctionDef) and node.name == "_test_notify")
    namespace = {"__package__": "jc", "ServiceCall": object, "hass": fake_hass,
                 "DOMAIN": "jarvis", "_LOGGER": logging.getLogger("test.diagnostic"),
                 "entry": types.SimpleNamespace(entry_id="example", options={}, data={})}
    exec(compile(ast.Module(body=[handler], type_ignores=[]), str(path), "exec"), namespace)

    async def invoke(svc):
        fake_hass.data["jarvis"] = {"example": {"runtime_config": {"notify_service": svc}}}
        return await namespace["_test_notify"](None)
    return invoke


@pytest.mark.parametrize("service", [
    "", None, "notify.example", "script.example", "scene.example",
    "automation.example", "esphome.example", "notify.example\n",
    "notify.*", ["notify.example"],
])
async def test_real_routes_deny_without_independent_policy(
    notify_route, service, fake_hass, policy, ha_error, caplog,
):
    try:
        result = await notify_route(service)
    except ha_error as exc:
        assert "not explicitly authorized" in str(exc)
    else:
        if result is not None:
            assert result["ok"] is False
    assert fake_hass.service_calls == []
    assert caplog.records


async def test_real_routes_allow_exact_endpoint(notify_route, fake_hass, policy):
    policy["notification_service_allowlist"] = ["notify.example"]
    result = await notify_route("notify.example")
    assert len(fake_hass.service_calls) == 1
    domain, service, payload = fake_hass.service_calls[0]
    assert (domain, service) == ("notify", "example")
    assert set(payload) <= {"message", "title", "data"}
    assert isinstance(payload["message"], str)
    if result is not None:
        assert result["ok"] is True


@pytest.mark.parametrize("raw", [
    "notify.example", {"notify.example": True}, [None], ["notify.example", "script.example"],
    ["notify.example", "notify.other\n"], ["notify.example", "notify.*"],
])
async def test_real_routes_malformed_policy_denies_whole_list(
    notify_route, raw, fake_hass, policy, ha_error,
):
    policy["notification_service_allowlist"] = raw
    try:
        result = await notify_route("notify.example")
    except ha_error:
        pass
    else:
        if result is not None:
            assert result["ok"] is False
    assert fake_hass.service_calls == []


@pytest.mark.parametrize("failure", [RuntimeError("endpoint failed"), False,
                                    {"ok": False}, {"error": "rejected"}, {"unexpected": True}])
async def test_real_routes_surface_handler_failure(
    notify_route, failure, fake_hass, policy, monkeypatch, ha_error, caplog,
):
    policy["notification_service_allowlist"] = ["notify.example"]

    async def fail(domain, service, payload, **kwargs):
        fake_hass.service_calls.append((domain, service, payload))
        assert kwargs["blocking"] is True
        if isinstance(failure, Exception):
            raise failure
        return failure
    monkeypatch.setattr(fake_hass.services, "async_call", fail)
    try:
        result = await notify_route("notify.example")
    except ha_error as exc:
        assert "fail" in str(exc)
    else:
        if result is not None:
            assert result["ok"] is False
    assert len(fake_hass.service_calls) == 1
    assert "failed" in caplog.text or "returned failure" in caplog.text


@pytest.mark.parametrize("payload", [
    {"message": "hello", "target": ["example"]},
    {"message": "hello", "entity_id": "all"},
    {"message": "hello", "data": {"target": "all"}},
    {"message": "command_activity"},
    {"message": " command_broadcast_intent "},
    {"message": None}, {"message": ""}, {"message": "hello", "title": []},
    {"message": "hello", "data": []},
    {"message": "hello", "data": {"attachment": {"url": "example", "target": "all"}}},
])
async def test_output_payload_cannot_expand_targets_or_execute_commands(
    load, fake_hass, policy, payload,
):
    policy["notification_service_allowlist"] = ["notify.example"]
    result = await load("output_dispatch").async_notify(fake_hass, "notify.example", payload)
    assert result["ok"] is False
    assert fake_hass.service_calls == []


async def test_bounded_image_and_driving_metadata_preserved(load, fake_hass, policy):
    policy["notification_service_allowlist"] = ["notify.example"]
    payload = {"message": "Example alert", "title": "Example",
               "data": {"image": "https://example.invalid/image",
                        "attachment": {"url": "https://example.invalid/image"},
                        "car_ui": True, "channel": "example", "importance": "high",
                        "ttl": 0, "priority": "high"}}
    assert (await load("output_dispatch").async_notify(fake_hass, "notify.example", payload))["ok"]
    assert fake_hass.service_calls == [("notify", "example", payload)]


@pytest.mark.parametrize("service", ["notify.notify", "notify.send_message", "script.example"])
async def test_generic_broadcast_and_wrong_domain_denied_even_when_listed(
    load, fake_hass, policy, service,
):
    policy["notification_service_allowlist"] = [service]
    assert not (await load("output_dispatch").async_notify(
        fake_hass, service, {"message": "hello"}))["ok"]
    assert fake_hass.service_calls == []


@pytest.mark.parametrize("allow", [False, True])
async def test_discovery_and_fallback_each_require_authorization(load, fake_hass, policy, allow):
    module = load("cognitive_core")
    fake_hass.services.register("notify", "mobile_app_unapproved")
    if allow:
        policy["notification_service_allowlist"] = ["notify.example"]
    result = await module._notify_all_devices(
        fake_hass, {"notify_service": "notify.example"}, "Example alert", "arrival")
    assert result["ok"] is allow
    assert [call[:2] for call in fake_hass.service_calls] == ([("notify", "example")] if allow else [])


async def test_failed_approved_discovery_cannot_fallback_to_unapproved_endpoint(
    load, fake_hass, policy, monkeypatch,
):
    policy["notification_service_allowlist"] = ["notify.mobile_app_example"]
    fake_hass.services.register("notify", "mobile_app_example")

    async def fail(domain, service, payload, **kwargs):
        fake_hass.service_calls.append((domain, service, payload))
        raise RuntimeError("delivery failed")
    monkeypatch.setattr(fake_hass.services, "async_call", fail)
    result = await load("cognitive_core")._notify_all_devices(
        fake_hass, {"notify_service": "script.example"}, "Example alert", "arrival")
    assert not result["ok"]
    assert [call[:2] for call in fake_hass.service_calls] == [("notify", "mobile_app_example")]


async def test_fixed_persistent_output_preserved_without_push_policy(load, fake_hass, policy):
    fake_hass.services.register("notify", "mobile_app_unapproved")
    result = await load("cognitive_core")._notify_all_devices(
        fake_hass, {}, "Example alert", "intrusion_confirmed")
    assert not result["ok"]  # This result reports push, not persistent UI delivery.
    assert [call[:2] for call in fake_hass.service_calls] == [("persistent_notification", "create")]


async def test_native_failure_does_not_call_configured_custom_fallback(
    load, fake_hass, monkeypatch,
):
    voice = load("voice_confirm")
    monkeypatch.setattr(
        voice, "_cfg",
        lambda *args: pytest.fail("listening must not consult configurable fallback"),
    )

    async def fail_native(domain, service, payload, **kwargs):
        fake_hass.service_calls.append((domain, service, payload))
        raise RuntimeError("native unavailable")
    monkeypatch.setattr(fake_hass.services, "async_call", fail_native)
    assert await voice._start_listening(fake_hass, "assist_satellite.example") is False
    assert [call[:2] for call in fake_hass.service_calls] == [
        ("assist_satellite", "start_conversation")]


@pytest.mark.parametrize(("values", "service", "payload"), [
    ({}, "notify.example", {"message": "Example alert"}),
    ({"notification_service_allowlist": ["notify.example", None]},
     "notify.example", {"message": "Example alert"}),
    ({"notification_service_allowlist": ["notify.example"]},
     "notify.example", {"message": "command_activity"}),
    ({"notification_service_allowlist": ["notify.example"]},
     "notify.example", {"message": "Example alert", "target": "all"}),
])
async def test_direct_guarded_sink_never_grants_authority(
    load, fake_hass, policy, values, service, payload,
):
    policy.update(values)
    result = await load("output_dispatch")._dispatch(
        fake_hass, service, payload)
    assert result["ok"] is False
    assert result["error"]
    assert fake_hass.service_calls == []


async def test_followup_reports_native_listening_failure_without_custom_dispatch(
    load, fake_hass, monkeypatch,
):
    voice = load("voice_confirm")
    monkeypatch.setattr(voice, "_mode", lambda h: "gated")
    monkeypatch.setattr(voice, "_satellite_for_entity", lambda *a: "assist_satellite.example")
    monkeypatch.setattr(voice, "_speaker_for_satellite", lambda *a: (None, []))

    async def fail_native(domain, service, payload, **kwargs):
        fake_hass.service_calls.append((domain, service, payload))
        assert kwargs["blocking"] is True
        raise RuntimeError("native unavailable")
    monkeypatch.setattr(fake_hass.services, "async_call", fail_native)
    result = await voice.ask_followup(fake_hass, "Example question")
    assert result["ok"] is False
    assert "Native satellite listening is unavailable" in result["error"]
    assert [call[:2] for call in fake_hass.service_calls] == [
        ("assist_satellite", "start_conversation")]


async def test_native_satellite_works_without_configurable_authority(load, fake_hass, policy):
    assert await load("voice_confirm")._start_listening(
        fake_hass, "assist_satellite.example") is True
    assert [call[:2] for call in fake_hass.service_calls] == [
        ("assist_satellite", "start_conversation")]


async def test_native_non_success_cannot_report_success_or_authorize_fallback(
    load, fake_hass, policy, monkeypatch,
):
    voice = load("voice_confirm")
    monkeypatch.setattr(voice, "_cfg", lambda h, k, d=None: {
        "voice_confirm_mode": "native",
    }.get(k, d))
    monkeypatch.setattr(voice, "_satellite_for_entity", lambda *a: "assist_satellite.example")
    monkeypatch.setattr(voice, "_speaker_for_satellite", lambda *a: (None, []))

    async def not_success(domain, service, payload, **kwargs):
        fake_hass.service_calls.append((domain, service, payload))
        return {"ok": False, "error": "unavailable"}
    monkeypatch.setattr(fake_hass.services, "async_call", not_success)
    result = await voice.ask_followup(fake_hass, "Example question")
    assert result["ok"] is False
    assert result["error"]
    assert all(call[0] == "assist_satellite" for call in fake_hass.service_calls)


async def test_unreadable_policy_is_logged_and_denies_without_dispatch(
    load, fake_hass, monkeypatch, caplog,
):
    config = load("jarvis_config")

    def broken(*args):
        raise RuntimeError("config unavailable")
    monkeypatch.setattr(config, "get", broken)
    output = load("output_dispatch")
    assert not (await output.async_notify(
        fake_hass, "notify.example", {"message": "Example alert"}))["ok"]
    assert fake_hass.service_calls == []
    assert "error accessing config" in caplog.text
