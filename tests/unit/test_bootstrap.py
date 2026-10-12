"""Tests for the in-process bootstrap (v6.28.0).

The live Supervisor/voice/pipeline effects can't run in this sandbox (no
Supervisor, no aiohttp), so these cover the orchestration *guards* (the safety
gates that protect a real HA), the run-once marker, the voice short-circuit, and
the in-process Wyoming/engine logic. Module-level aiohttp imports are stubbed.
"""
import sys
import types
from types import SimpleNamespace

import pytest

# Stub aiohttp + the HA aiohttp client helper before bootstrap is imported.
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
def bootstrap(load):
    return load("bootstrap")


@pytest.fixture
def jarvis_config(load):
    return load("jarvis_config")


@pytest.fixture(autouse=True)
def _isolate_fs(tmp_path, monkeypatch, bootstrap):
    from pathlib import Path
    monkeypatch.setattr(bootstrap, "MARKER_PATH", Path(tmp_path / ".bootstrap_done"))
    monkeypatch.setattr(bootstrap, "PIPER_DIR", Path(tmp_path / "piper"))
    yield


# ── supervisor detection ─────────────────────────────────────────────────────

def test_is_supervised_reflects_token(bootstrap, monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    assert bootstrap.is_supervised() is False
    monkeypatch.setenv("SUPERVISOR_TOKEN", "tok")
    assert bootstrap.is_supervised() is True
    assert bootstrap.supervisor_token() == "tok"


# ── run-once marker ──────────────────────────────────────────────────────────

def test_marker_roundtrip(bootstrap):
    assert bootstrap._read_marker() == {}
    bootstrap._write_marker("6.28.0", {"addons_ok": True, "voice_ok": True})
    m = bootstrap._read_marker()
    assert m["version"] == "6.28.0" and m["addons_ok"] is True


# ── voice short-circuit (no network) ─────────────────────────────────────────

def test_voice_present_detects_existing(bootstrap):
    q = "medium"
    bootstrap.PIPER_DIR.mkdir(parents=True, exist_ok=True)
    onnx = bootstrap.PIPER_DIR / f"en_GB-jarvis-{q}.onnx"
    js = bootstrap.PIPER_DIR / f"en_GB-jarvis-{q}.onnx.json"
    onnx.write_bytes(b"x" * (bootstrap.MIN_ONNX_SIZE + 10))
    js.write_text("{}")
    assert bootstrap._voice_present(q) is True
    assert bootstrap._voice_present("high") is False  # only medium present


# ── async_run_bootstrap guards (the safety gates) ────────────────────────────

@pytest.mark.asyncio
async def test_skips_when_flag_disabled(bootstrap, jarvis_config, fake_hass, monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "tok")
    monkeypatch.setattr(jarvis_config, "get",
                        lambda k, d=None: False if k == "auto_bootstrap" else d)
    status = await bootstrap.async_run_bootstrap(fake_hass)
    assert status["skipped"] == "auto_bootstrap disabled"
    assert status["addons_ok"] is False


@pytest.mark.asyncio
async def test_skips_without_supervisor(bootstrap, jarvis_config, fake_hass, monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.setattr(jarvis_config, "get",
                        lambda k, d=None: True if k == "auto_bootstrap" else d)
    status = await bootstrap.async_run_bootstrap(fake_hass)
    assert status["supervised"] is False
    assert "Supervisor" in status["skipped"]


@pytest.mark.asyncio
async def test_skips_by_default_without_opt_in(bootstrap, jarvis_config, fake_hass, monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "tok")
    monkeypatch.setattr(jarvis_config, "get", lambda k, d=None: d)
    async def _unexpected(*args, **kwargs):
        raise AssertionError("bootstrap side effects require explicit consent")
    monkeypatch.setattr(bootstrap, "_ensure_addon", _unexpected)
    monkeypatch.setattr(bootstrap, "_download_voice", _unexpected)
    monkeypatch.setattr(bootstrap, "_create_pipeline", _unexpected)
    status = await bootstrap.async_run_bootstrap(fake_hass)
    assert status["skipped"] == "auto_bootstrap disabled"
    assert status["addons_ok"] is False


@pytest.mark.parametrize("value, expected", [
    (None, False),
    (False, False),
    ("true", False),
    (True, True),
])
def test_opt_in_requires_explicit_boolean_true(
    bootstrap, jarvis_config, monkeypatch, value, expected,
):
    monkeypatch.setattr(
        jarvis_config, "get",
        lambda key, default=None: value if key == "auto_bootstrap" else default,
    )
    assert bootstrap.is_opted_in("auto_bootstrap") is expected


@pytest.mark.asyncio
async def test_skips_when_already_bootstrapped(bootstrap, jarvis_config, fake_hass, monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "tok")
    monkeypatch.setattr(jarvis_config, "get",
                        lambda k, d=None: True if k == "auto_bootstrap" else d)
    version = bootstrap._current_version()
    bootstrap._write_marker(version, {"addons_ok": True, "voice_ok": True})
    status = await bootstrap.async_run_bootstrap(fake_hass)
    assert status["skipped"] == "already bootstrapped this version"


@pytest.mark.asyncio
async def test_force_overrides_marker(bootstrap, jarvis_config, fake_hass, monkeypatch):
    # force=True must NOT early-return on the marker; it should proceed past the
    # marker gate (and then do real work, which we cut short by failing addons).
    monkeypatch.setenv("SUPERVISOR_TOKEN", "tok")
    monkeypatch.setattr(jarvis_config, "get",
                        lambda k, d=None: True if k == "auto_bootstrap" else d)
    bootstrap._write_marker(bootstrap._current_version(), {"addons_ok": True, "voice_ok": True})

    async def _no_addon(hass, slug, friendly):
        return False
    monkeypatch.setattr(bootstrap, "_ensure_addon", _no_addon)

    async def _no_voice(hass, quality):
        return False
    monkeypatch.setattr(bootstrap, "_download_voice", _no_voice)
    monkeypatch.setattr(bootstrap, "_reload_wyoming",
                        lambda hass: _async_return(0))
    monkeypatch.setattr(bootstrap, "_wait_for_agent",
                        lambda hass, **kw: _async_return(None))

    status = await bootstrap.async_run_bootstrap(fake_hass, force=True)
    assert status["skipped"] is None          # did not skip on marker
    assert status["addons_ok"] is False        # ran phase 1


# ── in-process Wyoming reload ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reload_wyoming_reloads_each_entry(bootstrap):
    reloaded = []

    class _Entries:
        def async_entries(self, domain):
            assert domain == "wyoming"
            return [SimpleNamespace(entry_id="w1"), SimpleNamespace(entry_id="w2")]

        async def async_reload(self, eid):
            reloaded.append(eid)

    hass = SimpleNamespace(config_entries=_Entries())
    n = await bootstrap._reload_wyoming(hass)
    assert n == 2 and reloaded == ["w1", "w2"]


# ── engine / agent discovery ─────────────────────────────────────────────────

def test_find_engine_prefers_hint(bootstrap, fake_hass):
    fake_hass.states.set("stt.faster_whisper", "idle")
    fake_hass.states.set("stt.something_else", "idle")
    assert bootstrap._find_engine(fake_hass, "stt", "whisper") == "stt.faster_whisper"


def test_find_engine_falls_back_to_first(bootstrap, fake_hass):
    fake_hass.states.set("tts.piper", "idle")
    assert bootstrap._find_engine(fake_hass, "tts", "piper") == "tts.piper"
    # no match for hint → first available
    assert bootstrap._find_engine(fake_hass, "tts", "nope") == "tts.piper"


def _async_return(value):
    async def _coro():
        return value
    return _coro()


def test_create_pipeline_points_agent_at_jarvis(bootstrap):
    """The JARVIS pipeline must run JARVIS's own conversation entity.
    async_create_default_pipeline leaves the agent on HA's default (an LLM
    integration), and then JARVIS's reply routing never runs — so the bootstrap
    must set conversation_engine=agent on both a new pipeline and an existing one
    (repair in place, not "leave as-is"), without selecting it as HA's preferred
    pipeline."""
    import inspect
    src = inspect.getsource(bootstrap._create_pipeline)
    assert "async_update_pipeline" in src
    assert "conversation_engine=agent" in src
    assert "leaving as-is" not in src
    assert "async_set_preferred" not in src
    assert "set_preferred" not in src
    # existing pipeline matched case-insensitively so "Jarvis (English)" is caught
    assert '.lower()' in src


def test_ensure_pipeline_agent_repairs_by_name_or_voice(bootstrap):
    """The every-startup repair must catch a JARVIS pipeline by name OR its JARVIS
    voice, skip when already correct, set the agent via async_update_pipeline, and
    run outside the Supervisor/marker gate (so it can't be raced or skipped)."""
    import inspect
    src = inspect.getsource(bootstrap.async_ensure_pipeline_agent)
    assert "async_update_pipeline" in src
    assert "conversation_engine=agent" in src
    assert "tts_voice" in src               # matches by JARVIS voice too
    assert "== agent" in src                # idempotent: skip when already right
    sched = inspect.getsource(bootstrap.schedule_bootstrap)
    assert "async_ensure_pipeline_agent" in sched   # wired to run every start


@pytest.mark.asyncio
@pytest.mark.parametrize("consent, should_update", [(False, False), (True, True)])
async def test_pipeline_repair_requires_consent_and_only_updates_jarvis(
    bootstrap, jarvis_config, fake_hass, monkeypatch, consent, should_update,
):
    monkeypatch.setattr(
        jarvis_config, "get",
        lambda key, default=None: consent if key == "auto_pipeline" else default,
    )
    updates = []
    jarvis_pipeline = SimpleNamespace(
        name="JARVIS", tts_voice="en_GB-jarvis-medium",
        conversation_engine="conversation.old",
    )
    unrelated_pipeline = SimpleNamespace(
        name="Home", tts_voice="en_US-amy", conversation_engine="conversation.old",
    )
    assist_pipeline = types.ModuleType("homeassistant.components.assist_pipeline")
    assist_pipeline.async_get_pipelines = lambda hass: [unrelated_pipeline, jarvis_pipeline]

    async def _update(hass, pipeline, **kwargs):
        updates.append((pipeline, kwargs))

    assist_pipeline.async_update_pipeline = _update
    components = sys.modules["homeassistant.components"]
    monkeypatch.setattr(components, "assist_pipeline", assist_pipeline, raising=False)
    monkeypatch.setattr(bootstrap, "_wait_for_agent", lambda *a, **k: _async_return("conversation.jarvis"))

    await bootstrap.async_ensure_pipeline_agent(fake_hass)
    assert bool(updates) is should_update
    if updates:
        assert updates == [(jarvis_pipeline, {"conversation_engine": "conversation.jarvis"})]


@pytest.mark.asyncio
async def test_pipeline_opt_in_can_create_without_addon_bootstrap(
    bootstrap, jarvis_config, fake_hass, monkeypatch,
):
    import sys

    monkeypatch.setattr(
        jarvis_config, "get",
        lambda key, default=None: True if key == "auto_pipeline" else default,
    )
    assist_pipeline = types.ModuleType("homeassistant.components.assist_pipeline")
    assist_pipeline.async_get_pipelines = lambda hass: []
    monkeypatch.setattr(
        sys.modules["homeassistant.components"], "assist_pipeline",
        assist_pipeline, raising=False,
    )
    monkeypatch.setattr(
        bootstrap, "_wait_for_agent",
        lambda *args, **kwargs: _async_return("conversation.jarvis"),
    )
    created = []

    async def _create(hass, quality):
        created.append(quality)
        return True

    monkeypatch.setattr(bootstrap, "_create_pipeline", _create)
    await bootstrap.async_ensure_pipeline_agent(fake_hass)
    assert created == ["medium"]


@pytest.mark.asyncio
async def test_pipeline_creation_keeps_piper_default_when_jarvis_voice_missing(
    bootstrap, fake_hass, monkeypatch,
):
    import sys

    monkeypatch.setattr(bootstrap, "_find_jarvis_agent", lambda hass: "conversation.jarvis")
    monkeypatch.setattr(
        bootstrap, "_find_engine",
        lambda hass, domain, hint: f"{domain}.{hint}",
    )
    monkeypatch.setattr(bootstrap, "_voice_present", lambda quality: False)

    pipeline = SimpleNamespace(name="JARVIS")
    updates = []
    assist_pipeline = types.ModuleType("homeassistant.components.assist_pipeline")

    async def _create(*args, **kwargs):
        return pipeline

    async def _update(hass, target, **kwargs):
        updates.append(kwargs)

    assist_pipeline.async_get_pipelines = lambda hass: []
    assist_pipeline.async_create_default_pipeline = _create
    assist_pipeline.async_update_pipeline = _update
    monkeypatch.setattr(
        sys.modules["homeassistant.components"], "assist_pipeline",
        assist_pipeline, raising=False,
    )

    async def _executor(func, *args):
        return func(*args)

    monkeypatch.setattr(fake_hass, "async_add_executor_job", _executor)
    assert await bootstrap._create_pipeline(fake_hass, "medium") is True
    assert updates == [{"conversation_engine": "conversation.jarvis"}]
