"""MCU Phase H exit-criteria gate — scripts/kernel_bypass_check.py.

Proves the gate (a) passes on the real tree — every world-mutating service call
converges on the universal seam or is classified — and (b) actually catches a new
direct device actuation, so a future bypass can't land silently.
"""
import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "kernel_bypass_check", ROOT / "scripts" / "kernel_bypass_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = _load_gate()


def test_tree_has_no_unclassified_bypasses():
    rows = gate.scan()
    violations = [r for r in rows if not r["ok"]]
    assert violations == [], (
        "direct service or Assist API tool calls missing from the inventory: "
        + "; ".join(f"{r['file']}:{r['line']} {r['func']}()" for r in violations))


def test_only_guarded_call_in_seam_file_is_allowed():
    call = {"domain": None, "service": None, "func": "guarded_call"}
    ok, _ = gate._classify("actuation.py", call)
    assert ok is True

    unguarded = {**call, "func": "direct_call"}
    ok, reason = gate._classify("actuation.py", unguarded)
    assert ok is False and "unlisted" in reason


def test_inventory_allows_only_the_listed_communication_site():
    call = {"domain": "notify", "service": None, "func": "_dispatch"}
    ok, _ = gate._classify("output_dispatch.py", call)
    assert ok is True

    ok, reason = gate._classify("new_module.py", call)
    assert ok is False and "unlisted" in reason


def test_assist_api_tool_dispatch_inventory_is_callsite_scoped():
    call = {"kind": "assist_api_tool", "func": "_execute_tool"}
    ok, _ = gate._classify("agent.py", call)
    assert ok is True

    ok, reason = gate._classify("new_module.py", call)
    assert ok is False and "unlisted" in reason


def test_inventory_detects_extra_assist_api_tool_calls(tmp_path, monkeypatch):
    component = tmp_path / "jarvis"
    component.mkdir()
    (component / "agent.py").write_text(
        "async def _execute_tool(api, first, second):\n"
        "    await api.async_call_tool(first)\n"
        "    await api.async_call_tool(second)\n",
        encoding="utf-8")
    monkeypatch.setattr(gate, "_component_dir", lambda: component)
    monkeypatch.setattr(gate, "_EXPECTED_CALLS", {})
    monkeypatch.setattr(gate, "_EXPECTED_TOOL_CALLS", {
        ("agent.py", "_execute_tool"): (1, "read-only gate"),
    })

    errors = [row for row in gate.scan() if row.get("inventory_error")]
    assert len(errors) == 1
    assert "expected 1, found 2" in errors[0]["reason"]


def test_inventory_detects_extra_identical_calls(tmp_path, monkeypatch):
    component = tmp_path / "jarvis"
    component.mkdir()
    (component / "output_dispatch.py").write_text(
        "async def _dispatch(hass, first, second):\n"
        "    await hass.services.async_call('notify', first)\n"
        "    await hass.services.async_call('notify', second)\n",
        encoding="utf-8")
    monkeypatch.setattr(gate, "_component_dir", lambda: component)
    monkeypatch.setattr(gate, "_EXPECTED_CALLS", {
        ("output_dispatch.py", "_dispatch", "notify", None):
            (1, "validated notification service policy"),
    })
    monkeypatch.setattr(gate, "_EXPECTED_TOOL_CALLS", {})

    errors = [row for row in gate.scan() if row.get("inventory_error")]
    assert len(errors) == 1
    assert "expected 1, found 2" in errors[0]["reason"]


@pytest.mark.parametrize("dom,svc", [
    ("light", "turn_on"), ("lock", "lock"), ("cover", "close_cover"),
    ("climate", "set_temperature"), ("switch", "turn_off"),
])
def test_new_direct_device_call_is_a_violation(dom, svc):
    # A new world-mutating device call in some ordinary module, not seam-routed
    # and not classified, must fail the gate.
    ok, reason = gate._classify("some_new_module.py",
                                {"domain": dom, "service": svc, "func": "_do"})
    assert ok is False and "unlisted" in reason


def test_dynamic_domain_in_unknown_site_is_a_violation():
    # domain=None (a variable) in an unclassified (file, func) is a violation —
    # forces the author to classify or seam-route.
    ok, _ = gate._classify("some_new_module.py",
                           {"domain": None, "service": None, "func": "_mystery"})
    assert ok is False
