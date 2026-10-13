"""Automation persistence is denied before input handling, file IO or HA reload."""
import ast
import logging
from pathlib import Path
import sys
import types

import pytest


@pytest.fixture
def creator(load, monkeypatch):
    module = load("automation_creator")
    monkeypatch.setattr(sys.modules["jc"], "automation_creator", module, raising=False)
    return module


class NoWriteHass:
    def __init__(self):
        self.path_calls = []
        self.executor_calls = []
        self.service_calls = []
        self.events = []
        self.config = types.SimpleNamespace(path=self.path)
        self.services = types.SimpleNamespace(async_call=self.call)
        self.bus = types.SimpleNamespace(async_fire=lambda *args: self.events.append(args))

    def path(self, *args):
        self.path_calls.append(args)
        raise AssertionError("Policy denial must precede config path lookup")

    async def async_add_executor_job(self, *args):
        self.executor_calls.append(args)
        raise AssertionError("Policy denial must precede executor/file work")

    async def call(self, *args, **kwargs):
        self.service_calls.append((args, kwargs))
        raise AssertionError("Policy denial must precede automation.reload")


@pytest.mark.parametrize("inputs", [
    {},
    {"trigger": [], "action": []},
    {"trigger": {"platform": "time"}, "action": {"service": "light.turn_on",
                                               "target": {"area_id": "example"}}},
    {"trigger": "{{ trigger }}", "action": [{"service": "script.example"}]},
    {"trigger": [{"platform": "event"}], "action": [
        {"choose": [{"sequence": [{"service": "automation.trigger"}]}]}]},
    {"trigger": True, "action": False, "condition": "bad", "mode": "parallel"},
])
@pytest.mark.parametrize("existing", [
    None, b"", b"- id: example\n  alias: Keep unchanged\n", b"not: [valid",
])
async def test_installation_denied_with_no_io_or_yaml_mutation(
    creator, tmp_path, inputs, existing, caplog,
):
    path = tmp_path / "automations.yaml"
    if existing is not None:
        path.write_bytes(existing)
    hass = NoWriteHass()
    result = await creator.create_automation(hass, alias="Example", **inputs)
    assert result == {"success": False, "error": creator.AUTOMATION_INSTALLATION_ERROR}
    assert hass.path_calls == hass.executor_calls == hass.service_calls == hass.events == []
    assert path.exists() is (existing is not None)
    if existing is not None:
        assert path.read_bytes() == existing
    assert "disabled by policy" in caplog.text


async def test_denial_does_not_inspect_or_normalize_alias(creator):
    class InvalidAlias:
        def lower(self):
            raise AssertionError("Do not normalize denied input")
    hass = NoWriteHass()
    assert not (await creator.create_automation(hass, alias=InvalidAlias()))["success"]
    assert hass.path_calls == hass.executor_calls == hass.service_calls == []


async def test_ha_creation_handler_raises_without_writes_reload_or_success_event(
    creator, tmp_path, monkeypatch,
):
    errors = types.ModuleType("homeassistant.exceptions")
    errors.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "homeassistant.exceptions", errors)
    path = tmp_path / "automations.yaml"
    original = b"- id: example\n  alias: Do not replace\n"
    path.write_bytes(original)
    hass = NoWriteHass()
    source = Path(__file__).resolve().parents[2] / "custom_components" / "jarvis" / "__init__.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    handler = next(node for node in ast.walk(tree)
                   if isinstance(node, ast.AsyncFunctionDef) and node.name == "_create_automation")
    namespace = {"__package__": "jc", "ServiceCall": object, "hass": hass,
                 "_LOGGER": logging.getLogger("test.automation")}
    exec(compile(ast.Module(body=[handler], type_ignores=[]), str(source), "exec"), namespace)
    call = types.SimpleNamespace(data={
        "alias": "Example", "trigger": {"platform": "time"},
        "action": {"service": "script.example"},
    })
    with pytest.raises(errors.HomeAssistantError, match="disabled by policy"):
        await namespace["_create_automation"](call)
    assert hass.path_calls == hass.executor_calls == hass.service_calls == hass.events == []
    assert path.read_bytes() == original
