#!/usr/bin/env python3
"""MCU Phase H exit-criteria gate — zero consequential actuator bypasses.

Phase H's exit criterion is that **every consequential (world-mutating) actuation
converges on the universal actuator seam** (``actuation.execute_actuator`` /
``execute_safety_actuator``), so each one is planned, event-published and
journaled. This gate is the honest, mechanical proof of that: it AST-scans the
integration for ``*.services.async_call(...)`` and
``hass_api.async_call_tool(...)``. It fails CI if a direct service call or
indirect Assist API tool dispatch is outside the exact reviewed inventory.

It is the runtime sibling of the 8.34.0 governance gate (which classifies agent
*tools*): same "classify or wire" philosophy, applied to raw service calls. A new
direct ``light``/``lock``/``cover``/``climate``/… call therefore cannot land
uncounted — the author must either route it through the seam or classify it here
with a reason.

Classification is an exact inventory keyed by component-relative path,
enclosing function, and literal domain/service. Dynamic arguments remain limited
to their exact documented call site. Expected call counts catch extra or removed
calls, including duplicates at an otherwise-approved site.

Pure stdlib; no Home Assistant import. Run ``--check`` in CI; bare run lists every
call and its classification.
"""
from __future__ import annotations

import ast
import pathlib
import sys

# Exact dispatch inventory, keyed by component-relative path, enclosing function,
# and literal domain/service. A None value represents a dynamic argument, but
# remains restricted to this exact site. Counts detect extra identical calls.
_EXPECTED_CALLS = {
    ("__init__.py", "async_setup_entry", "persistent_notification", "create"): (1, "startup recovery notification"),
    ("__init__.py", "_jarvis_backup", "persistent_notification", "create"): (1, "explicit backup completion notification"),
    ("__init__.py", "_jarvis_restore", "persistent_notification", "create"): (1, "explicit restore completion notification"),
    ("actuation.py", "guarded_call", None, None): (1, "sole direct actuator dispatch seam"),
    ("agent.py", "_exec_weather_forecast", "weather", "get_forecasts"): (2, "read-only forecast request and fallback"),
    ("cognitive_core.py", "_notify_all_devices", "persistent_notification", "create"): (1, "confirmed-intrusion notification"),
    ("continued_conversation.py", "_reopen_after_speaker", "assist_satellite", "start_conversation"): (1, "reopen selected voice satellite"),
    ("observer.py", "_speak", "tts", "speak"): (1, "observer TTS output"),
    ("output_dispatch.py", "_dispatch", "notify", None): (1, "validated notification service policy"),
    ("proactive_audio.py", "_speak_tts", "tts", "speak"): (2, "proactive TTS and bounded fallback"),
    ("proactive_audio.py", "_run_audit", None, None): (1, "fixed jarvis.speak audit announcement"),
    ("tts_helper.py", "async_announce", "tts", "speak"): (2, "TTS batch output and bounded fallback"),
    ("voice_confirm.py", "_confirm_native", "assist_satellite", "ask_question"): (1, "native confirmation prompt"),
    ("voice_confirm.py", "_start_listening", "assist_satellite", "start_conversation"): (1, "bounded confirmation follow-up"),
    ("voice_confirm.py", "ask_followup", "assist_satellite", "start_conversation"): (1, "bounded voice follow-up"),
    ("voice_confirm.py", "announce_test", "assist_satellite", "announce"): (1, "explicit voice-output diagnostic"),
}

_EXPECTED_TOOL_CALLS = {
    ("agent.py", "_execute_tool"): (1, "HA Assist fallback is read-only-gated"),
    ("conversation.py", "_agentic_loop"): (1, "advertised and executed tools are read-only-gated"),
}


def _component_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "jarvis"


class _Scanner(ast.NodeVisitor):
    def __init__(self, filename: str):
        self.filename = filename
        self.func_stack: list[str] = []
        self.calls: list[dict] = []

    def visit_FunctionDef(self, node):
        self.func_stack.append(node.name)
        self.generic_visit(node)
        self.func_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):
        func = node.func
        function = self.func_stack[-1] if self.func_stack else "<module>"
        if isinstance(func, ast.Attribute) and func.attr == "async_call_tool":
            self.calls.append({
                "kind": "assist_api_tool", "line": node.lineno,
                "func": function, "domain": None, "service": None,
            })
        elif (isinstance(func, ast.Attribute) and func.attr == "async_call"
              and isinstance(func.value, ast.Attribute)
              and func.value.attr == "services"):
            domain = self._literal(node.args[0]) if node.args else None
            service = self._literal(node.args[1]) if len(node.args) > 1 else None
            self.calls.append({
                "kind": "service", "line": node.lineno, "func": function,
                "domain": domain, "service": service,
            })
        self.generic_visit(node)

    @staticmethod
    def _literal(node):
        return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _classify(filename: str, call: dict) -> tuple[bool, str]:
    if call.get("kind", "service") == "assist_api_tool":
        expected = _EXPECTED_TOOL_CALLS.get((filename, call["func"]))
        if expected:
            return True, expected[1]
        return False, f"unlisted HA Assist API tool dispatch in {filename}:{call['func']}()"
    key = (filename, call["func"], call["domain"], call["service"])
    expected = _EXPECTED_CALLS.get(key)
    if expected:
        return True, expected[1]
    dom, svc = call["domain"], call["service"]
    where = f"{dom}.{svc}" if dom or svc else "<dynamic domain/service>"
    return False, f"unlisted direct service call {where} in {filename}:{call['func']}()"


def scan() -> list[dict]:
    comp = _component_dir()
    rows: list[dict] = []
    observed_services: dict[tuple, int] = {}
    observed_tools: dict[tuple, int] = {}
    for path in sorted(comp.rglob("*.py")):
        if "kernel" in path.relative_to(comp).parts[:-1]:
            continue
        rel = path.relative_to(comp).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except Exception as exc:   # pragma: no cover - defensive
            rows.append({"file": rel, "line": 0, "func": "<parse>",
                         "ok": False, "reason": f"parse error: {exc}"})
            continue
        sc = _Scanner(rel)
        sc.visit(tree)
        for call in sc.calls:
            if call["kind"] == "assist_api_tool":
                key = (rel, call["func"])
                observed_tools[key] = observed_tools.get(key, 0) + 1
            else:
                key = (rel, call["func"], call["domain"], call["service"])
                observed_services[key] = observed_services.get(key, 0) + 1
            ok, reason = _classify(rel, call)
            rows.append({"file": rel, "line": call["line"], "func": call["func"],
                         "kind": call["kind"], "ok": ok, "reason": reason})

    for key, (expected_count, _reason) in _EXPECTED_CALLS.items():
        actual_count = observed_services.get(key, 0)
        if actual_count != expected_count:
            filename, function, domain, service = key
            rows.append({
                "file": filename, "line": 0, "func": function, "ok": False,
                "inventory_error": True,
                "reason": (f"service inventory count drift for {domain}.{service}: "
                           f"expected {expected_count}, found {actual_count}"),
            })
    for key, (expected_count, _reason) in _EXPECTED_TOOL_CALLS.items():
        actual_count = observed_tools.get(key, 0)
        if actual_count != expected_count:
            filename, function = key
            rows.append({
                "file": filename, "line": 0, "func": function, "ok": False,
                "inventory_error": True,
                "reason": (f"HA Assist tool inventory count drift: expected "
                           f"{expected_count}, found {actual_count}"),
            })
    return rows


def main(argv: list[str]) -> int:
    rows = scan()
    violations = [r for r in rows if not r["ok"]]
    if "--check" not in argv:
        for r in sorted(rows, key=lambda r: (r["file"], r["line"])):
            mark = "ok " if r["ok"] else "XX "
            print(f"  {mark}{r['file']}:{r['line']} {r['func']}() — {r['reason']}")
        call_count = sum(row.get("kind") == "service" for row in rows)
        tool_count = sum(row.get("kind") == "assist_api_tool" for row in rows)
        print(f"\r\n{call_count} service calls, {tool_count} HA Assist tool calls, "
              f"{len(violations)} inventory violations")
    if "--check" in argv:
        if violations:
            print("ACTUATOR BYPASS — direct calls are unlisted or the dispatch "
                  "inventory has drifted:", file=sys.stderr)
            for r in violations:
                print(f"  - {r['file']}:{r['line']} {r['func']}() — {r['reason']}",
                      file=sys.stderr)
            print("\r\nRoute device actuation through the shared seam; update the "
                  "exact inventory and docs for an intentional non-actuator call.",
                  file=sys.stderr)
            return 1
        service_count = sum(row.get("kind") == "service" for row in rows)
        tool_count = sum(row.get("kind") == "assist_api_tool" for row in rows)
        print(f"bypass gate OK — all {service_count} service calls and "
              f"{tool_count} HA Assist tool calls are inventoried "
              f"(Phase H exit criterion)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
