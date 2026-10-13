"""Script, scene and automation dispatch remains unavailable to JARVIS.

These tests ensure even a generic exact-entity allowlist cannot authorize those
execution domains or produce an actuation event.
"""
import json
import sys
import types

import pytest

if "homeassistant.helpers.llm" not in sys.modules:
    _llm = types.ModuleType("homeassistant.helpers.llm")
    _llm.async_get_api = lambda *a, **k: None
    sys.modules["homeassistant.helpers.llm"] = _llm


@pytest.fixture
def agent(load):
    return load("agent")


@pytest.fixture
def published(load, monkeypatch):
    events = load("events")
    sink = []
    monkeypatch.setattr(events, "publish", lambda hass, ev: sink.append(ev))
    return sink


@pytest.fixture
def allow(load, monkeypatch):
    """Explicitly allowlist the exact entities these tests drive."""
    jc = load("jarvis_config")
    ids = ["scene.movie_night", "script.bedtime", "automation.away"]
    monkeypatch.setattr(jc, "get", lambda k, d=None:
                        ids if k == "actuation_allowlist" else d)


async def test_scene_script_denied_without_allowlist(agent, fake_hass, published):
    fake_hass.states.set("script.bedtime", "off")
    out = await agent._exec_run_scene_script(fake_hass, {"entity_id": "script.bedtime"})
    assert "success" not in json.loads(out) or json.loads(out)["success"] is False
    assert fake_hass.service_calls == []
    assert published == []


async def test_entity_allowlist_cannot_authorize_scene(agent, fake_hass, published, allow):
    fake_hass.states.set("scene.movie_night", "scening", area="living")
    out = await agent._exec_run_scene_script(
        fake_hass, {"entity_id": "scene.movie_night"})
    res = json.loads(out)
    assert "not permitted" in res["error"]
    assert fake_hass.service_calls == []
    assert published == []


async def test_entity_allowlist_cannot_authorize_script(agent, fake_hass, published, allow):
    fake_hass.states.set("script.bedtime", "off")
    out = await agent._exec_run_scene_script(
        fake_hass, {"entity_id": "script.bedtime"})
    assert "not permitted" in json.loads(out)["error"]
    assert fake_hass.service_calls == []
    assert published == []


async def test_entity_allowlist_cannot_authorize_automation(
        agent, fake_hass, published, allow):
    fake_hass.states.set("automation.away", "on")
    out = await agent._exec_run_scene_script(
        fake_hass, {"entity_id": "automation.away"})
    assert "not permitted" in json.loads(out)["error"]
    assert fake_hass.service_calls == []
    assert published == []


async def test_invalid_target_errors_without_envelope(agent, fake_hass, published):
    out = await agent._exec_run_scene_script(
        fake_hass, {"entity_id": "light.den"})
    assert "Not a scene/script/automation" in out
    assert published == []
