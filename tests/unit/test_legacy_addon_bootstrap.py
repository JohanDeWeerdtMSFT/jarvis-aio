"""Consent-boundary tests for the reference legacy add-on bootstrap runner."""
import importlib.util
from pathlib import Path
import sys

import pytest


@pytest.fixture
def legacy_bootstrap():
    script = Path(__file__).resolve().parents[2] / "scripts" / "legacy_addon_bootstrap.py"
    name = "_jarvis_legacy_addon_bootstrap_test"
    spec = importlib.util.spec_from_file_location(name, script)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


async def _no_sleep(_delay):
    return None


@pytest.mark.asyncio
@pytest.mark.parametrize("flags", [
    {},
    {"JARVIS_AUTO_BOOTSTRAP": "false", "JARVIS_AUTO_PIPELINE": "false"},
    {"JARVIS_AUTO_BOOTSTRAP": "TRUE", "JARVIS_AUTO_PIPELINE": "TRUE"},
])
async def test_legacy_defaults_and_non_true_flags_make_no_host_writes(
    legacy_bootstrap, monkeypatch, tmp_path, flags,
):
    for key in ("JARVIS_AUTO_BOOTSTRAP", "JARVIS_AUTO_PIPELINE"):
        monkeypatch.delenv(key, raising=False)
    for key, value in flags.items():
        monkeypatch.setenv(key, value)

    calls = []
    legacy_bootstrap.TOKEN = "test-token"
    legacy_bootstrap.STATUS_FILE = tmp_path / "status.json"
    monkeypatch.setattr(legacy_bootstrap, "ensure_addon",
                        lambda *args: calls.append(("addon", args)))
    monkeypatch.setattr(legacy_bootstrap, "download_jarvis_voice",
                        lambda *args: calls.append(("voice", args)))
    monkeypatch.setattr(legacy_bootstrap, "addon_restart",
                        lambda *args: calls.append(("restart", args)))
    monkeypatch.setattr(legacy_bootstrap, "reload_wyoming",
                        lambda: calls.append(("reload",)))
    monkeypatch.setattr(legacy_bootstrap, "ws_call",
                        lambda *args: calls.append(("websocket", args)))
    monkeypatch.setattr(legacy_bootstrap, "create_jarvis_pipeline",
                        lambda *args: calls.append(("pipeline", args)))

    assert await legacy_bootstrap.main() == 0
    assert calls == []


@pytest.mark.asyncio
async def test_legacy_bootstrap_consent_does_not_enable_pipeline_writes(
    legacy_bootstrap, monkeypatch, tmp_path,
):
    monkeypatch.setenv("JARVIS_AUTO_BOOTSTRAP", "true")
    monkeypatch.delenv("JARVIS_AUTO_PIPELINE", raising=False)
    legacy_bootstrap.TOKEN = "test-token"
    legacy_bootstrap.STATUS_FILE = tmp_path / "status.json"
    monkeypatch.setattr(legacy_bootstrap.asyncio, "sleep", _no_sleep)
    addons = []
    pipelines = []
    monkeypatch.setattr(legacy_bootstrap, "ensure_addon",
                        lambda *args: addons.append(args) or True)
    monkeypatch.setattr(legacy_bootstrap, "download_jarvis_voice", lambda *args: True)
    monkeypatch.setattr(legacy_bootstrap, "addon_restart", lambda *args: True)
    monkeypatch.setattr(legacy_bootstrap, "wait_for_addon_state", lambda *a, **k: True)

    async def _reload():
        return None

    async def _ws_call(*args):
        raise AssertionError("agent lookup should be skipped without pipeline consent")

    async def _pipeline(*args):
        pipelines.append(args)
        return True

    monkeypatch.setattr(legacy_bootstrap, "reload_wyoming", _reload)
    monkeypatch.setattr(legacy_bootstrap, "ws_call", _ws_call)
    monkeypatch.setattr(legacy_bootstrap, "create_jarvis_pipeline", _pipeline)

    assert await legacy_bootstrap.main() == 0
    assert len(addons) == len(legacy_bootstrap.REQUIRED_ADDONS)
    assert pipelines == []


@pytest.mark.asyncio
async def test_legacy_pipeline_consent_does_not_enable_addon_writes(
    legacy_bootstrap, monkeypatch, tmp_path,
):
    monkeypatch.delenv("JARVIS_AUTO_BOOTSTRAP", raising=False)
    monkeypatch.setenv("JARVIS_AUTO_PIPELINE", "true")
    legacy_bootstrap.TOKEN = "test-token"
    legacy_bootstrap.STATUS_FILE = tmp_path / "status.json"
    calls = []
    monkeypatch.setattr(legacy_bootstrap, "ensure_addon",
                        lambda *args: calls.append(("addon", args)))
    monkeypatch.setattr(legacy_bootstrap, "download_jarvis_voice",
                        lambda *args: calls.append(("voice", args)))
    monkeypatch.setattr(legacy_bootstrap, "addon_restart",
                        lambda *args: calls.append(("restart", args)))
    monkeypatch.setattr(legacy_bootstrap, "reload_wyoming",
                        lambda: calls.append(("reload",)))

    async def _ws_call(*args):
        return [{"result": [{"id": "conversation.jarvis"}]}]

    async def _pipeline(*args):
        calls.append(("pipeline", args))
        return True

    monkeypatch.setattr(legacy_bootstrap, "ws_call", _ws_call)
    monkeypatch.setattr(legacy_bootstrap, "create_jarvis_pipeline", _pipeline)

    assert await legacy_bootstrap.main() == 0
    assert [name for name, _ in calls] == ["pipeline"]


@pytest.mark.asyncio
async def test_legacy_pipeline_creation_leaves_preferred_pipeline_unchanged(
    legacy_bootstrap, monkeypatch,
):
    command_batches = []

    async def _ws_call(commands):
        command_batches.append(commands)
        if len(command_batches) == 1:
            return [
                {"result": {"agents": [{"id": "conversation.jarvis"}]}},
                {"result": {"providers": [{"engine_id": "stt.whisper"}]}},
                {"result": {"providers": [{"engine_id": "tts.piper"}]}},
                {"result": {"pipelines": []}},
            ]
        return [{"success": True, "result": {"pipeline_id": "jarvis-pipeline"}}]

    monkeypatch.setattr(legacy_bootstrap, "ws_call", _ws_call)
    assert await legacy_bootstrap.create_jarvis_pipeline("medium") is True
    assert len(command_batches) == 2
    assert all(
        command["type"] != "assist_pipeline/pipeline/set_preferred"
        for batch in command_batches
        for command in batch
    )
