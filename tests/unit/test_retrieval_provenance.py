"""Issue #1: retrieved/retained text never becomes control authority.

Synthetic data and fake providers only; no live HA or provider endpoints.
"""
import json

import pytest

from test_grounded_isolation import (  # noqa: F401  (flow is a fixture)
    INJECTION, ScriptedProvider, call, flow, reply)

CONTROL = call("control_device", entity_id="light.kitchen", action="turn_on")


@pytest.mark.parametrize("lookup", [
    call("search_entities", query="kitchen"),
    call("get_entity_state", entity_id="light.kitchen"),
])
async def test_malicious_friendly_name_in_tool_output_cannot_control(flow, lookup):
    flow.hass.states.set("light.kitchen", "off", friendly_name=INJECTION)
    provider = ScriptedProvider([reply("", lookup), reply("", CONTROL), reply("Done")])
    result = await flow.run(provider, [{"role": "user", "content": "Find the kitchen"}])
    assert INJECTION in provider.requests[0][0][0]["content"]
    assert flow.hass.service_calls == []
    assert "refused" in result.lower()


async def test_friendly_name_replayed_in_later_turn_cannot_control(flow):
    flow.hass.states.set("light.kitchen", "off", friendly_name=INJECTION)
    first = ScriptedProvider([
        reply("", call("search_entities", query="kitchen")),
        reply("Found it."),
    ])
    await flow.run(first, [{"role": "user", "content": "Find the kitchen"}])
    replay = flow.agent._flatten_tool_calls_for_replay(first.requests[-1][0][1:])
    assert any(INJECTION in m["content"] for m in replay)
    later = ScriptedProvider([reply("", CONTROL), reply("Done")])
    result = await flow.run(
        later, replay + [{"role": "user", "content": "Do what it said"}])
    assert flow.hass.service_calls == []
    assert "refused" in result.lower()


async def test_summary_is_labelled_untrusted_and_cannot_control(flow):
    provider = ScriptedProvider([
        reply("", call("web_research", query="the answer")),
        reply("The answer is 42. " + INJECTION),
    ])
    answer = await flow.run(provider, [{"role": "user", "content": "Search"}])
    history = [{"role": "assistant", "content": answer}] + [
        {"role": "user" if i % 2 == 0 else "assistant", "content": "context"}
        for i in range(flow.agent.SUMMARIZE_THRESHOLD)
    ] + [{"role": "user", "content": "Continue"}]
    later = ScriptedProvider([reply(INJECTION), reply("", CONTROL), reply("Done")])
    result = await flow.run(later, history)
    summary = [m["content"] for m in later.requests[1][0]
               if m["role"] == "system" and "Previous conversation" in m["content"]]
    assert summary and "never instructions" in summary[0] and INJECTION in summary[0]
    assert flow.hass.service_calls == []
    assert "refused" in result.lower()


async def test_slim_retry_with_retained_search_history_cannot_control(flow):
    provider = ScriptedProvider([
        Exception("HTTP 413 Payload Too Large"),
        reply("", CONTROL),
        reply("Done"),
    ])
    history = [
        {"role": "user", "content": "Search for the answer"},
        {"role": "assistant", "content": "The answer is 42. " + INJECTION},
        {"role": "user", "content": "Follow the source"},
    ]
    result = await flow.run(provider, history)
    assert len(provider.requests) >= 3
    assert all(flow.agent._is_read_only_tool(t["function"]["name"])
               for _, tools in provider.requests for t in tools or [])
    assert flow.hass.service_calls == []
    assert "refused" in result.lower()


@pytest.mark.parametrize("source", ["read_email", "search_documents", "calendar_agenda"])
async def test_every_retrieval_source_is_inert_for_control(flow, source):
    provider = ScriptedProvider([
        reply("", call(source, query="x")), reply("", CONTROL), reply("Done")])
    result = await flow.run(provider, [{"role": "user", "content": "Check it"}])
    assert flow.hass.service_calls == []
    assert "refused" in result.lower()


async def test_every_mutating_registered_tool_is_refused_in_scope(flow, load):
    boundary = load("grounded_boundary")
    mutating = sorted(n for n in flow.agent._TOOL_MAP
                      if not flow.agent._is_read_only_tool(n))
    assert {"control_device", "bulk_control", "execute_plan"} <= set(mutating)

    results = []

    # The decorator replaces the answer with the denial text; capture outcomes
    # through the closure instead.
    @boundary.read_only_reasoning
    async def capture():
        for name in mutating:
            results.append(json.loads(
                await flow.agent._execute_tool(flow.hass, name, {})))
        return "ok"

    assert await capture() == boundary.DENIAL
    assert len(results) == len(mutating)
    assert all(r.get("error") == boundary.DENIAL for r in results)
    assert flow.hass.service_calls == []


async def test_exact_pair_authorization_is_not_usable_from_grounded_scope(
        flow, load, monkeypatch):
    cfg = load("jarvis_config")
    monkeypatch.setattr(cfg, "get", lambda key, default=None: {
        "actuation_service_allowlist": {"switch.heater": ["switch.turn_on"]},
    }.get(key, default))
    flow.hass.states.set("switch.heater", "off", friendly_name=INJECTION)
    gate = load("actuation_gate")
    assert gate.authorize(
        flow.hass, "switch", "turn_on", {"entity_id": "switch.heater"})[0]
    provider = ScriptedProvider([
        reply("", call("web_research", query="x")),
        reply("", call("control_device", entity_id="switch.heater", action="turn_on")),
        reply("Done"),
    ])
    result = await flow.run(provider, [{"role": "user", "content": "Search"}])
    assert flow.hass.service_calls == []
    assert "refused" in result.lower()
    # The same pair stays authorized outside grounded reasoning.
    assert gate.authorize(
        flow.hass, "switch", "turn_on", {"entity_id": "switch.heater"})[0]
