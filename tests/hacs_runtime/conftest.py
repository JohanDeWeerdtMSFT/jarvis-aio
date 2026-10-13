"""Opt-in isolated artifact tests, separate from source-tree integration tests."""
import os
from pathlib import Path

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")
if not os.environ.get("HACS_TEST_COMPONENTS_PATH"):
    pytest.skip("requires the pinned temporary HACS distribution", allow_module_level=True)

import custom_components  # noqa: E402


@pytest.fixture(autouse=True)
def installed_component_paths(hass, monkeypatch, enable_custom_integrations):
    """HA must discover installed artifacts, never the checkout's JARVIS."""
    distribution = Path(os.environ["HACS_TEST_COMPONENTS_PATH"]).resolve()
    assert (distribution / "hacs" / "manifest.json").is_file()
    installed = Path(hass.config.path("custom_components"))
    installed.mkdir(exist_ok=True)
    monkeypatch.setattr(custom_components, "__path__", [str(distribution), str(installed)])
    yield
