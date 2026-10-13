"""Automation installation boundary: suggestions and YAML remain advisory-only."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

AUTOMATION_INSTALLATION_ERROR = (
    "Automation installation is disabled by policy. Suggestions and YAML are "
    "advisory-only; no Home Assistant automation was written or reloaded."
)


async def create_automation(
    hass: HomeAssistant,
    *,
    alias: str,
    description: str = "",
    trigger: list[dict] | dict | None = None,
    condition: list[dict] | dict | None = None,
    action: list[dict] | dict | None = None,
    mode: str = "single",
) -> dict[str, Any]:
    """Deny every installation attempt before inspecting inputs or accessing HA."""
    _LOGGER.warning("JARVIS: %s", AUTOMATION_INSTALLATION_ERROR)
    return {"success": False, "error": AUTOMATION_INSTALLATION_ERROR}
