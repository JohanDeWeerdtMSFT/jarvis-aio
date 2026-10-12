"""Issue #378 — a camera→Gemini vision call stuck in the Google GenAI SDK's retry
``time.sleep()`` tied up a Home Assistant executor (SyncWorker) thread; stacked
calls exhausted the pool and froze the instance.

The fix is two layers:
  1. every provider request is bounded (per-request timeout + capped retries) so
     a hung/flaky provider can't block an executor thread for minutes, and
  2. concurrent camera LLM calls are capped by a semaphore so, however slow a
     provider is, camera analysis can never occupy more than a couple of executor
     threads and starve the rest of HA.
"""
import asyncio
import sys
import threading
import types
from concurrent.futures import ThreadPoolExecutor

import pytest


# ── layer 1: provider per-request ceilings ───────────────────────────────────

@pytest.fixture
def llm(load):
    return load("llm_provider")


def test_provider_timeout_constants_are_bounded(llm):
    assert 0 < llm.PROVIDER_HTTP_TIMEOUT_S <= 120
    assert llm.PROVIDER_MAX_RETRIES >= 0
    # Gemini's ceiling is expressed to the SDK in MILLISECONDS.
    assert llm.GEMINI_HTTP_TIMEOUT_MS == int(llm.PROVIDER_HTTP_TIMEOUT_S * 1000)


def test_gemini_http_options_bounds_timeout_and_retries(llm):
    opts = llm._gemini_http_options(None)
    assert opts["timeout"] == llm.GEMINI_HTTP_TIMEOUT_MS            # ms, per SDK
    assert opts["retry_options"]["attempts"] == llm.PROVIDER_MAX_RETRIES
    assert "base_url" not in opts
    # an explicit base_url (e.g. a proxy) is preserved alongside the ceilings
    with_base = llm._gemini_http_options("http://gw.local/v1")
    assert with_base["base_url"] == "http://gw.local/v1"
    assert with_base["timeout"] == llm.GEMINI_HTTP_TIMEOUT_MS


# ── layer 2: camera LLM concurrency cap ───────────────────────────────────────

@pytest.fixture
def cam(load, monkeypatch):
    monkeypatch.setitem(sys.modules, "aiohttp", types.ModuleType("aiohttp"))
    hc = types.ModuleType("homeassistant.components.camera")
    hc.async_get_image = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "homeassistant.components.camera", hc)
    net = types.ModuleType("homeassistant.helpers.network")
    net.get_url = lambda *a, **k: "http://localhost:8123"
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.network", net)
    for sib, fns in {
        "jc.database": {"save_message": lambda *a, **k: None},
        "jc.tts_helper": {"async_announce": lambda *a, **k: None},
        "jc.camera_backends": {"find_backend": lambda *a, **k: None},
    }.items():
        m = types.ModuleType(sib)
        for n, f in fns.items():
            setattr(m, n, f)
        monkeypatch.setitem(sys.modules, sib, m)
    sys.modules.pop("jc.camera", None)
    mod = load("camera")
    yield mod
    sys.modules.pop("jc.camera", None)


class _ThreadHass:
    """A hass whose executor actually runs the call in a worker thread (with room
    to spare), so the concurrency cap — not the pool size — is what's observed."""
    def __init__(self, loop):
        loop.set_default_executor(ThreadPoolExecutor(max_workers=8))
    async def async_add_executor_job(self, fn, *a):
        return await asyncio.get_running_loop().run_in_executor(None, fn, *a)


def test_capped_camera_chat_passes_kwargs_through(cam):
    async def _run():
        captured = {}
        class _Client:
            def chat(self, **kw):
                captured.update(kw)
                return {"text": "ok"}
        hass = _ThreadHass(asyncio.get_running_loop())
        out = await cam._capped_camera_chat(
            hass, _Client(), messages=[1], max_tokens=7)
        assert out == {"text": "ok"}
        assert captured == {"messages": [1], "max_tokens": 7}
    asyncio.run(_run())


def test_capped_camera_chat_never_exceeds_the_cap(cam):
    async def _run():
        cap = cam.VISION_MAX_CONCURRENCY
        assert cap >= 1
        gate = threading.Event()
        lock = threading.Lock()
        active = {"now": 0, "max": 0}

        class _Client:
            def chat(self, **kw):
                with lock:
                    active["now"] += 1
                    active["max"] = max(active["max"], active["now"])
                gate.wait(3.0)
                with lock:
                    active["now"] -= 1
                return {"text": "ok"}

        hass = _ThreadHass(asyncio.get_running_loop())
        client = _Client()
        # Launch more calls than the cap; the executor has 8 free threads, so only
        # the semaphore can hold concurrency down to the cap.
        tasks = [asyncio.create_task(
                    cam._capped_camera_chat(hass, client, messages=[]))
                 for _ in range(cap + 3)]
        for _ in range(100):                       # wait (≤2s) for the cap to fill
            await asyncio.sleep(0.02)
            if active["max"] >= cap:
                break
        assert active["max"] == cap                # reached the cap, not more
        gate.set()
        results = await asyncio.gather(*tasks)
        assert all(r["text"] == "ok" for r in results)
        assert active["max"] <= cap                # never exceeded it — the invariant
    asyncio.run(_run())
