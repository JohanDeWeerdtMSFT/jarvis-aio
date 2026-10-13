"""
JARVIS — House routines (sleep / wake / away / home).

Each routine is a sequence of service calls that JARVIS orchestrates and
narrates. Configurable at runtime — users can override any step via
/config/jarvis_routines.yaml.
"""
from __future__ import annotations

import logging
import os

import yaml

from homeassistant.core import HomeAssistant, ServiceCall

from .paths import config_path_str
from .tts_helper import async_announce
from . import actuation, actuation_gate

_LOGGER = logging.getLogger(__name__)

ROUTINE_FILE = config_path_str("jarvis_routines.yaml")

# Sensible defaults — user can override by creating /config/jarvis_routines.yaml
DEFAULT_ROUTINES: dict[str, list[dict]] = {
    "goodnight": [
        {"service": "light.turn_off", "target": {"entity_id": "all"}, "announce": "Turning off lights, {honorific}."},
        {"service": "lock.lock",      "target": {"area_id": "all"},   "announce": "Locking up."},
        {"service": "cover.close_cover", "target": {"device_class": "shade"}, "announce": "Closing the shades."},
        # Scene for final state — users should define scene.nighttime or similar
        {"service": "scene.turn_on",  "data": {"entity_id": "scene.nighttime"}, "optional": True},
        {"announce": "Goodnight, {honorific}."},
    ],
    "goodmorning": [
        {"service": "cover.open_cover", "target": {"device_class": "shade"}, "announce": "Opening the shades, {honorific}."},
        {"service": "scene.turn_on",    "data": {"entity_id": "scene.morning"}, "optional": True},
        {"announce": "Good morning, {honorific}. I hope you slept well."},
    ],
    "leaving": [
        {"service": "light.turn_off",  "target": {"entity_id": "all"}, "announce": "Shutting everything down, {honorific}."},
        {"service": "climate.set_preset_mode", "data": {"preset_mode": "eco"}, "target": {"entity_id": "all"}, "optional": True},
        {"service": "lock.lock",       "target": {"area_id": "all"}},
        {"announce": "Locked up. Have a good one, {honorific}."},
    ],
    "arriving": [
        {"service": "scene.turn_on",  "data": {"entity_id": "scene.welcome"}, "optional": True, "announce": "Welcome home, {honorific}."},
        {"service": "climate.set_preset_mode", "data": {"preset_mode": "home"}, "target": {"entity_id": "all"}, "optional": True},
    ],
}


def _load_routines() -> dict[str, list[dict]]:
    """Load user routines from file if present, else use defaults."""
    if os.path.exists(ROUTINE_FILE):
        try:
            with open(ROUTINE_FILE) as f:
                user_routines = yaml.safe_load(f) or {}
            if isinstance(user_routines, dict):
                merged = {**DEFAULT_ROUTINES, **user_routines}
                _LOGGER.debug("JARVIS: loaded %d user routines", len(user_routines))
                return merged
        except Exception as exc:
            _LOGGER.warning("JARVIS: could not parse %s: %s", ROUTINE_FILE, exc)
    return DEFAULT_ROUTINES


async def async_run_routine(
    hass: HomeAssistant,
    call: ServiceCall,
    honorific: str,
    tts_entity: str | None,
    speakers: list[str],
) -> dict:
    """
    Service: jarvis.routine
    Run a named routine by iterating through its steps.
    """
    if actuation_gate._cfg("routine_execution_enabled", False) is not True:
        _LOGGER.warning("JARVIS: routine execution is disabled")
        return {"success": False, "error": "routine_execution_disabled",
                "steps_executed": 0, "errors": ["Routine execution is disabled"]}
    name: str = call.data["name"].lower().strip()
    routines = await hass.async_add_executor_job(_load_routines)

    if name not in routines:
        _LOGGER.warning("JARVIS: unknown routine '%s'", name)
        msg = f"I don't know a routine called {name}, {honorific}."
        await async_announce(hass, msg, tts_entity, speakers)
        return {"success": False, "error": "unknown_routine"}

    steps = routines[name]
    prepared = []
    try:
        if not isinstance(steps, list):
            raise ValueError("routine must contain a list of steps")
        for step in steps:
            if not isinstance(step, dict):
                raise ValueError("routine step must be a mapping")
            service = step.get("service")
            data = {}
            if service is not None:
                if not isinstance(service, str) or service.count(".") != 1:
                    raise ValueError("invalid routine service")
                domain, svc = service.split(".")
                raw_data = step.get("data", {})
                target = step.get("target", {})
                if not isinstance(raw_data, dict) or not isinstance(target, dict):
                    raise ValueError("routine data and target must be mappings")
                if set(target) - {"entity_id"}:
                    raise ValueError("routine target expansion is not permitted")
                data = dict(raw_data)
                if target:
                    if "entity_id" in data and data["entity_id"] != target["entity_id"]:
                        raise ValueError("conflicting routine entity targets")
                    data.update(target)
                allowed, reason = actuation_gate.authorize(hass, domain, svc, data)
                if not allowed:
                    raise PermissionError(reason)
            prepared.append((step, service, data))
    except (ValueError, PermissionError) as exc:
        _LOGGER.warning("JARVIS: routine '%s' denied before dispatch: %s", name, exc)
        return {"success": False, "routine": name, "steps_executed": 0,
                "errors": [str(exc)]}

    _LOGGER.info("JARVIS: running routine '%s' (%d steps)", name, len(steps))

    errors = []
    executed = 0
    for step, service, data in prepared:
        try:
            if service:
                domain, svc = service.split(".", 1)
                ok, detail = await actuation.execute_actuator(
                    hass, capability=service, entity_id=data["entity_id"],
                    domain=domain, service=svc, data=data, action=svc,
                    blocking=True)
                if not ok:
                    raise RuntimeError(f"{service}: {detail}")
                executed += 1
            announce_text = step.get("announce")
            if announce_text:
                text = announce_text.format(honorific=honorific)
                await async_announce(hass, text, tts_entity, speakers)
        except Exception as exc:
            _LOGGER.warning("JARVIS: routine step error: %s", exc)
            errors.append(str(exc))
            break

    return {
        "success": not errors,
        "routine": name,
        "steps_executed": executed,
        "errors": errors,
    }


async def async_run_routine_service(
    hass: HomeAssistant,
    call: ServiceCall,
    honorific: str,
    tts_entity: str | None,
    speakers: list[str],
) -> dict:
    """Run a routine and surface any unsuccessful result as an HA service error."""
    result = await async_run_routine(hass, call, honorific, tts_entity, speakers)
    if not isinstance(result, dict) or result.get("success") is not True:
        details = result.get("errors") if isinstance(result, dict) else None
        if not details and isinstance(result, dict):
            details = result.get("error", "invalid routine result")
        if isinstance(details, (list, tuple)):
            details = "; ".join(str(item) for item in details)
        from homeassistant.exceptions import HomeAssistantError
        raise HomeAssistantError(
            f"Routine {getattr(call, 'data', {}).get('name', '')!r} failed: "
            f"{details or 'unknown error'}")
    return result


def list_routines() -> list[str]:
    """Return names of available routines."""
    return list(_load_routines().keys())
