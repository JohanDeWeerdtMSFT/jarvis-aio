"""Deterministic authorization gate for the final actuator/service-dispatch boundary.

Calls routed through the actuator seam, agent plans and control retries are
checked here, *after* target resolution
(direct entity ids, learned aliases, area expansion, plan steps). Nothing in the
decision depends on prompts, wake words, voice confirmation or the LLM:

* the (domain, service) pair must be in a fixed table, and the entity's domain
  must match the service domain;
* the call must target exactly one concrete entity id (no ``all``, lists,
  comma-separated ids, or area/device/floor/label targets);
* services that could open, unlock, disarm, trigger arbitrary code (script,
  scene, automation) or drive other security-sensitive classes are denied unless
  the exact entity id appears in ``actuation_allowlist`` in the JARVIS config;
* the allowlist is validated strictly. Any malformed value disables the whole
  list (fail closed), it never widens access. Wildcards are not supported;
* switches and input booleans require exact entity/service pairs in
  ``actuation_service_allowlist``; names and device classes grant no authority.

Lock, close-cover and alarm-arm operations stay permitted by default to preserve
existing safety/lockdown paths. They are not universally harmless, and this
foundation does not cover every direct service caller or indirect automation.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

_LOGGER = logging.getLogger(__name__)

ALLOWLIST_KEY = "actuation_allowlist"
HA_TOOL_ALLOWLIST_KEY = "ha_api_tool_allowlist"
SERVICE_ALLOWLIST_KEY = "actuation_service_allowlist"

_ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+\Z")
_TOOL_RE = re.compile(r"^[A-Za-z0-9_]{1,64}\Z")

# Allowed without any configuration: low-impact services, plus securing actions.
_BASE: dict[str, frozenset] = {
    "light": frozenset({"turn_on", "turn_off", "toggle"}),
    "fan": frozenset({"turn_on", "turn_off", "toggle", "set_percentage"}),
    "climate": frozenset({"set_temperature", "set_hvac_mode", "turn_on", "turn_off"}),
    "humidifier": frozenset({"turn_on", "turn_off", "set_humidity"}),
    "vacuum": frozenset({"start", "pause", "stop", "return_to_base"}),
    "media_player": frozenset({
        "turn_on", "turn_off", "toggle", "media_play", "media_pause",
        "media_play_pause", "media_stop", "media_next_track",
        "media_previous_track", "volume_up", "volume_down", "volume_set",
        "volume_mute"}),
    "lock": frozenset({"lock"}),
    "cover": frozenset({"close_cover", "stop_cover"}),
    "alarm_control_panel": frozenset({
        "alarm_arm_home", "alarm_arm_away", "alarm_arm_night"}),
}

# Allowed only for an entity that is explicitly allowlisted.
_ELEVATED: dict[str, frozenset] = {
    "switch": frozenset({"turn_on", "turn_off", "toggle"}),
    "input_boolean": frozenset({"turn_on", "turn_off", "toggle"}),
    "lock": frozenset({"unlock", "open"}),
    "cover": frozenset({"open_cover", "toggle", "set_cover_position"}),
    "alarm_control_panel": frozenset({
        "alarm_disarm", "alarm_trigger", "alarm_arm_vacation",
        "alarm_arm_custom_bypass"}),
    "script": frozenset({"turn_on"}),
    "scene": frozenset({"turn_on"}),
    "automation": frozenset({"trigger"}),
    "siren": frozenset({"turn_on", "turn_off", "toggle"}),
    "valve": frozenset({"open_valve", "close_valve", "set_valve_position"}),
    "camera": frozenset({"turn_on", "turn_off"}),
}

# Cover device classes that are not an entry point to the home.
_SAFE_COVER_CLASSES = frozenset({
    "awning", "blind", "curtain", "damper", "shade", "shutter"})
_SAFE_COVER_OPENING = frozenset({"open_cover", "toggle", "set_cover_position"})

# Target keys that would widen a call beyond the single entity we authorized.
_FORBIDDEN_DATA_KEYS = frozenset({
    "area_id", "device_id", "floor_id", "label_id", "target"})

# HA Assist API tools that only read state.
HA_READ_ONLY_TOOLS = frozenset({
    "GetLiveContext", "GetDateTime", "HassGetState", "HassGetWeather"})


def _cfg(key: str, default: Any = None) -> Any:
    try:
        from . import jarvis_config
        return jarvis_config.get(key, default)
    except Exception as exc:
        _LOGGER.warning("actuation_gate: error accessing config key '%s': %s (failing closed)", key, exc)
        return default   # unreadable config is treated as "nothing allowlisted"


def _validated_list(key: str, pattern: "re.Pattern[str]") -> frozenset:
    raw = _cfg(key, None)
    if raw is None:
        return frozenset()
    if (not isinstance(raw, (list, tuple))
            or any(not isinstance(v, str) or not pattern.match(v) for v in raw)):
        _LOGGER.warning(
            "JARVIS: %s is invalid (expected a list of exact names); ignoring "
            "the whole list — nothing is allowlisted", key)
        return frozenset()
    return frozenset(raw)


def allowlist() -> frozenset:
    """Validated set of exact entity ids permitted for elevated services."""
    return _validated_list(ALLOWLIST_KEY, _ENTITY_RE)


def _service_permitted(target: str, domain: str, service: str) -> bool:
    """Require an exact entity/service pair; malformed policy denies all pairs."""
    raw = _cfg(SERVICE_ALLOWLIST_KEY)
    if raw is None:
        return False
    if isinstance(raw, dict):
        valid = True
        for entity, services in raw.items():
            if not isinstance(entity, str) or not _ENTITY_RE.fullmatch(entity):
                valid = False
                break
            entity_domain = entity.split(".", 1)[0]
            supported = _ELEVATED.get(entity_domain, frozenset())
            if (entity_domain not in ("switch", "input_boolean")
                    or not isinstance(services, (list, tuple))
                    or any(not isinstance(s, str)
                           or s not in {f"{entity_domain}.{v}" for v in supported}
                           for s in services)):
                valid = False
                break
        if valid:
            return f"{domain}.{service}" in raw.get(target, ())
    _LOGGER.warning("JARVIS: %s is invalid; denying all entity/service pairs",
                    SERVICE_ALLOWLIST_KEY)
    return False


def ha_tool_permitted(tool_name: str) -> bool:
    """HA Assist API tools are not routed through the actuator seam, so they are
    denied unless read-only or explicitly named in ``ha_api_tool_allowlist``."""
    if not isinstance(tool_name, str):
        return False
    if tool_name in HA_READ_ONLY_TOOLS:
        return True
    return tool_name in _validated_list(HA_TOOL_ALLOWLIST_KEY, _TOOL_RE)


def authorize(hass, domain: Any, service: Any, data: Any,
              entity_id: Optional[str] = None) -> tuple[bool, str]:
    """Return ``(allowed, reason)``. Pure, deterministic, fail closed."""
    try:
        if not isinstance(domain, str) or not isinstance(service, str):
            return False, "invalid service"
        if not isinstance(data, dict):
            return False, "invalid service data"
        target = data.get("entity_id")
        if not isinstance(target, str) or not _ENTITY_RE.match(target):
            return False, "call must target exactly one entity id"
        if entity_id is not None and entity_id != target:
            return False, "entity id mismatch"
        if _FORBIDDEN_DATA_KEYS & set(data):
            return False, "area/device/label targets are not permitted"
        if target.split(".", 1)[0] != domain:
            return False, f"{target} is not in domain {domain}"

        base = _BASE.get(domain, frozenset())
        elevated = _ELEVATED.get(domain, frozenset())
        if service not in base and service not in elevated:
            return False, f"{domain}.{service} is not permitted"

        if domain in ("switch", "input_boolean"):
            if _service_permitted(target, domain, service):
                return True, ""
            return False, (f"{domain}.{service} on {target} requires an exact "
                           f"entity/service pair in {SERVICE_ALLOWLIST_KEY}")

        if service in base:
            return True, ""

        if (domain == "cover" and service in _SAFE_COVER_OPENING
                and _cover_class(hass, target) in _SAFE_COVER_CLASSES):
            return True, ""

        if target in allowlist():
            return True, ""
        return False, (f"{domain}.{service} on {target} requires the entity to "
                       f"be listed in {ALLOWLIST_KEY}")
    except Exception as exc:   # pragma: no cover - defensive, fail closed
        return False, f"authorization error: {exc}"


def _cover_class(hass, entity_id: str) -> Optional[str]:
    try:
        st = hass.states.get(entity_id)
        cls = st.attributes.get("device_class") if st is not None else None
        return cls if isinstance(cls, str) else None
    except Exception:
        return None
