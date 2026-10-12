"""Bounded notification dispatch and Home Assistant result interpretation."""
from __future__ import annotations

import logging
from typing import Any

from .actuation_gate import notification_service_permitted

_LOGGER = logging.getLogger(__name__)
_NOTIFICATION_DATA_TYPES = {
    "image": str, "car_ui": bool, "channel": str, "importance": str,
    "ttl": int, "priority": str,
}


def _valid_notification(payload: Any) -> bool:
    if (not isinstance(payload, dict)
            or set(payload) - {"message", "title", "data"}
            or not isinstance(payload.get("message"), str)
            or not payload["message"].strip()
            or payload["message"].strip().startswith("command_")
            or ("title" in payload and not isinstance(payload["title"], str))):
        return False
    data = payload.get("data", {})
    if not isinstance(data, dict):
        return False
    for key, value in data.items():
        if key == "attachment":
            if (not isinstance(value, dict) or set(value) != {"url"}
                    or not isinstance(value["url"], str)):
                return False
        elif key not in _NOTIFICATION_DATA_TYPES or type(value) is not _NOTIFICATION_DATA_TYPES[key]:
            return False
    return True


def service_succeeded(result: Any) -> bool:
    """HA's no-response completion is None; explicit failures never mean success."""
    return (result is None or result is True
            or (isinstance(result, dict) and not result.get("error")
                and result.get("ok") is not False
                and result.get("success") is not False
                and (result.get("ok") is True or result.get("success") is True)))


async def _dispatch(hass, service: str, payload: dict) -> dict:
    if not notification_service_permitted(service):
        error = "Notification endpoint is not explicitly authorized"
    elif not _valid_notification(payload):
        error = "Notification payload is invalid or contains unsupported commands/targets"
    else:
        error = None
    if error:
        _LOGGER.warning("JARVIS: %s", error)
        return {"ok": False, "error": error}
    name = service.split(".", 1)[1]
    try:
        # Wait for the handler so scheduling a failed call is not reported as delivery.
        result = await hass.services.async_call("notify", name, payload, blocking=True)
    except Exception as exc:
        error = f"Output service {service} failed: {exc}"
        _LOGGER.warning(error)
        return {"ok": False, "error": error}
    if not service_succeeded(result):
        error = f"Output service {service} returned failure: {result}"
        _LOGGER.warning(error)
        return {"ok": False, "error": error}
    return {"ok": True}


async def async_notify(hass, service: str, payload: dict) -> dict:
    """Send only approved endpoint notifications with bounded display metadata."""
    return await _dispatch(hass, service, payload)


async def async_test_notify(hass, service: str) -> None:
    """HA diagnostic boundary: propagate denied or failed output as a service error."""
    result = await async_notify(hass, service, {
        "title": "JARVIS",
        "message": "This is a test notification from JARVIS. If you see this, phone notifications are working.",
    })
    if not result["ok"]:
        from homeassistant.exceptions import HomeAssistantError
        raise HomeAssistantError(result["error"])
