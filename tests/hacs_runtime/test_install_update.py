"""Original offline fixtures driving the unmodified HACS download command."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import time
from types import SimpleNamespace
from zipfile import ZipFile

from aioresponses import CallbackResult, aioresponses
from homeassistant.const import EVENT_CALL_SERVICE
from homeassistant.core import callback
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

BASELINE = "779fc8fc5bc58aedc73237b7dd122663bb0f9ae6"
REPOSITORY = "test-owner/jarvis-test"
ROOT = Path(__file__).resolve().parents[2]
COMMAND = "hacs/repository/download"


def _artifact(ref):
    sha = subprocess.check_output(
        ["git", "rev-parse", ref], cwd=ROOT, text=True
    ).strip()
    archive = subprocess.check_output(
        ["git", "archive", "--format=zip", sha, "custom_components/jarvis",
         "hacs.json", "README.md"],
        cwd=ROOT,
    )
    with ZipFile(io.BytesIO(archive)) as source:
        files = {name: source.read(name) for name in source.namelist()
                 if not name.endswith("/")}
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as target:
        for name, content in files.items():
            target.writestr(f"synthetic-repository-{sha}/{name}", content)
    return sha, files, buffer.getvalue()


class _GitHub:
    """Strict HTTP adapter: original public metadata, no real token or requests."""

    def __init__(self, old, candidate, hacs_manifest):
        self.artifacts = {
            ref: artifact for artifact in (old, candidate)
            for ref in (artifact[0], artifact[0][:7])
        }
        self.active = old
        self.hacs_files = {
            "hacs.json": b'{"content_in_root": false}',
            "custom_components/hacs/manifest.json": hacs_manifest,
            "README.md": b"# Synthetic HACS metadata\n",
        }
        self.requests = []
        self.unexpected = []
        self.downloaded = []

    def response(self, url, **kwargs):
        self.requests.append(str(url))
        parts = url.path.strip("/").split("/")
        if url.host == "data-v2.hacs.xyz" and url.path in {
            "/integration/data.json", "/plugin/data.json", "/template/data.json",
            "/theme/data.json", "/removed/data.json", "/critical/data.json",
        }:
            return CallbackResult(payload=[] if parts[0] in {"removed", "critical"} else {})
        if url.host == "api.github.com" and url.path == "/rate_limit":
            rate = {"limit": 5000, "remaining": 5000, "used": 0,
                    "reset": int(time.time()) + 3600}
            return CallbackResult(payload={"rate": rate, "resources": {"core": rate}})
        if url.host == "github.com" and parts[:2] == REPOSITORY.split("/"):
            if parts[2:] == ["archive", "refs", "tags", "main.zip"]:
                return CallbackResult(status=404, payload={"message": "No synthetic tag"})
            if parts[2:] == ["archive", "refs", "heads", "main.zip"]:
                self.downloaded.append(self.active[0])
                return CallbackResult(body=self.active[2], content_type="application/zip")
        if url.host in {"api.github.com", "raw.githubusercontent.com"}:
            offset = 1 if url.host == "api.github.com" else 0
            if offset and parts[0] != "repos":
                return self._unexpected(url)
            repository = "/".join(parts[offset:offset + 2])
            if repository not in {REPOSITORY, "hacs/integration"}:
                return self._unexpected(url)
            route = parts[offset + 2:]
            sha, files, _ = self.active
            if repository == "hacs/integration":
                sha, files = "c0dfd8b44297c3673c21973e2539375a53687a9c", self.hacs_files
            if url.host == "raw.githubusercontent.com":
                ref, *filename = route
                if repository == REPOSITORY and ref in self.artifacts:
                    sha, files, _ = self.artifacts[ref]
                content = files.get("/".join(filename))
                allowed_refs = {"main", sha, sha[:7]}
                if repository == "hacs/integration":
                    allowed_refs.add("2.0.5")
                if ref not in allowed_refs or content is None:
                    return self._unexpected(url)
                return CallbackResult(body=content, content_type="text/plain")
            if not route:
                return CallbackResult(payload={
                    "id": 101 if repository == REPOSITORY else 102,
                    "name": repository.split("/")[1], "full_name": repository,
                    "owner": {"login": repository.split("/")[0], "id": 1},
                    "default_branch": "main", "archived": False, "private": False,
                    "html_url": f"https://github.com/{repository}", "topics": [],
                    "description": "Synthetic offline fixture", "stargazers_count": 0,
                    "pushed_at": "2026-01-01T00:00:00Z",
                })
            if route == ["releases"]:
                return CallbackResult(payload=[])
            if route in (["commits"], ["commits", "main"]):
                commit = {"sha": sha, "commit": {
                    "message": "Synthetic default-branch update",
                    "committer": {"date": "2026-01-01T00:00:00Z"},
                }}
                return CallbackResult(payload=[commit] if len(route) == 1 else commit)
            if route == ["branches", "main"]:
                return CallbackResult(payload={"name": "main", "commit": {"sha": sha}})
            if route == ["git", "trees", "main"]:
                directories = {str(Path(name).parent).replace("\\", "/") for name in files}
                directories.add("custom_components")
                tree = [
                    {"path": name, "mode": "040000", "type": "tree", "sha": sha}
                    for name in sorted(directories) if name != "."
                ]
                tree.extend(
                    {"path": name, "mode": "100644", "type": "blob",
                     "sha": hashlib.sha1(b"blob " + str(len(content)).encode()
                                         + b"\0" + content).hexdigest(),
                     "size": len(content)}
                    for name, content in files.items()
                )
                return CallbackResult(payload={"sha": sha, "tree": tree, "truncated": False})
            if route[0] == "contents":
                name = "/".join(route[1:])
                if name in files and url.query.get("ref", "main") == "main":
                    return CallbackResult(payload={
                        "type": "file", "name": name.split("/")[-1], "path": name,
                        "encoding": "base64",
                        "content": base64.b64encode(files[name]).decode(),
                        "sha": sha, "size": len(files[name]),
                    })
        return self._unexpected(url)

    def _unexpected(self, url):
        self.unexpected.append(str(url))
        raise AssertionError(f"Unconfigured runtime HTTP request: {url}")


class _Connection:
    """Recording websocket transport; registered schema/admin/handler stay real."""

    def __init__(self):
        self.user = SimpleNamespace(is_admin=True)
        self.result = asyncio.get_running_loop().create_future()

    def send_message(self, message):
        self.result.set_result(message)

    def send_error(self, message_id, code, message):
        self.result.set_exception(AssertionError(f"{message_id}: {code}: {message}"))

    def async_handle_exception(self, message, exception):
        self.result.set_exception(exception)


async def _download(hass, repository_id, message_id):
    connection = _Connection()
    handler, schema = hass.data["websocket_api"][COMMAND]
    message = schema({"id": message_id, "type": COMMAND, "repository": repository_id})
    handler(hass, connection, message)
    result = await asyncio.wait_for(connection.result, timeout=30)
    assert result["id"] == message_id
    assert result["success"] is True
    await hass.async_block_till_done()


def _verify_files(installed, artifact):
    for name, content in artifact[1].items():
        prefix = "custom_components/jarvis/"
        if name.startswith(prefix):
            assert (installed / name[len(prefix):]).read_bytes() == content, name


class _Provider:
    name = "synthetic"

    def supports_vision(self):
        return False

    def chat(self, *args, **kwargs):
        raise AssertionError("Artifact lifecycle must not call a provider")


async def test_hacs_default_branch_install_update_and_consent(hass, monkeypatch):
    """Install old ZIP, advance synthetic main, update ZIP, load installed candidate."""
    old = await hass.async_add_executor_job(_artifact, BASELINE)
    candidate = await hass.async_add_executor_job(_artifact, "HEAD")
    assert old[0] != candidate[0]
    manifest_path = Path(os.environ["HACS_TEST_COMPONENTS_PATH"]) / "hacs" / "manifest.json"
    manifest = await hass.async_add_executor_job(manifest_path.read_bytes)
    assert json.loads(manifest)["version"] == "2.0.5"
    github = _GitHub(old, candidate, manifest)
    calls = []

    @callback
    def record(event):
        calls.append(dict(event.data))

    unsubscribe = hass.bus.async_listen(EVENT_CALL_SERVICE, record)
    hacs_entry = MockConfigEntry(domain="hacs", data={"token": ""}, unique_id="hacs")
    hacs_entry.add_to_hass(hass)
    jarvis_entry = None
    with aioresponses() as http:
        http.get(re.compile(r"^https?://"), callback=github.response, repeat=True)
        try:
            assert await async_setup_component(hass, "homeassistant", {})
            assert await hass.config_entries.async_setup(hacs_entry.entry_id)
            await hass.async_block_till_done()
            from custom_components.hacs.enums import HacsCategory, HacsStage

            hacs = hass.data["hacs"]
            assert not hacs.system.disabled
            assert hacs.stage == HacsStage.RUNNING
            await hacs.async_register_repository(REPOSITORY, HacsCategory.INTEGRATION)
            repository = hacs.repositories.get_by_full_name(REPOSITORY)
            assert repository is not None
            assert repository.data.releases is False
            assert repository.version_to_download() == "main"
            installed = Path(hass.config.path("custom_components", "jarvis"))
            assert not installed.exists()
            await _download(hass, repository.data.id, 1)
            assert repository.data.installed is True
            assert repository.data.installed_version is None
            await hass.async_add_executor_job(_verify_files, installed, old)
            old_commit = repository.data.installed_commit
            assert old_commit == old[0][:7]
            github.active = candidate
            await repository.update_repository(force=True)
            assert repository.pending_update
            await _download(hass, repository.data.id, 2)
            await hass.async_add_executor_job(_verify_files, installed, candidate)
            assert repository.data.installed_commit != old_commit
            assert repository.data.installed_commit == repository.data.last_commit
            assert repository.data.installed_commit == candidate[0][:7]
            assert repository.data.installed_version is None
            assert not repository.pending_update
            assert github.downloaded == [old[0], candidate[0]]
            assert not repository.data.published_tags

            jarvis = await hass.async_add_executor_job(
                importlib.import_module, "custom_components.jarvis"
            )
            assert Path(jarvis.__file__).resolve() == (installed / "__init__.py").resolve()
            monkeypatch.setattr(jarvis, "create_provider", lambda *a, **kw: _Provider())
            jarvis_entry = MockConfigEntry(
                domain="jarvis", unique_id="jarvis", options={},
                data={"schema_version": 7, "api_key": "", "model": "test",
                      "llm_provider": "ollama", "llm_base_url": "http://localhost:11434/v1"},
            )
            jarvis_entry.add_to_hass(hass)
            assert await async_setup_component(hass, "conversation", {})
            assert await hass.config_entries.async_setup(jarvis_entry.entry_id)
            await hass.async_block_till_done()
            from custom_components.jarvis.migrations import CURRENT_SCHEMA_VERSION

            assert jarvis_entry.data["schema_version"] == CURRENT_SCHEMA_VERSION == 8
            assert jarvis_entry.options["auto_bootstrap"] is False
            assert jarvis_entry.options["auto_pipeline"] is False
            migrated = (dict(jarvis_entry.data), dict(jarvis_entry.options))
            assert calls == []
            assert await hass.config_entries.async_reload(jarvis_entry.entry_id)
            await hass.async_block_till_done()
            assert (dict(jarvis_entry.data), dict(jarvis_entry.options)) == migrated
            assert calls == []
        finally:
            if jarvis_entry and jarvis_entry.entry_id in hass.data.get("jarvis", {}):
                assert await hass.config_entries.async_unload(jarvis_entry.entry_id)
            if "hacs" in hass.data:
                assert await hass.config_entries.async_unload(hacs_entry.entry_id)
            await hass.async_block_till_done()
            unsubscribe()
            assert github.unexpected == []
            assert {method.upper() for method, url in http.requests} == {"GET"}
    assert calls == []
