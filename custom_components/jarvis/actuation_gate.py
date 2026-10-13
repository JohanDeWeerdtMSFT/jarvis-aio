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
  explicitly authorized in the JARVIS config;
* the allowlist is validated strictly. Any malformed value disables the whole
  list (fail closed), it never widens access. Wildcards are not supported;
* switches, input booleans, locks, covers and alarm panels require exact
  entity/service pairs in ``actuation_service_allowlist``; names and device
  classes grant no authority.

There is no implicit securing-action exception. Lock/access and cover actions
are denied unless each entity/service pair is explicitly authorized. This gate
does not prove that an authorized switch or helper has no hazardous downstream
automation.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

_LOGGER = logging.getLogger(__name__)

ALLOWLIST_KEY = "actuation_allowlist"
SERVICE_ALLOWLIST_KEY = "actuation_service_allowlist"
NOTIFICATION_ALLOWLIST_KEY = "notification_service_allowlist"

_ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+\Z")
_NOTIFY_RE = re.compile(r"notify\.[a-z0-9_]+\Z")

# Allowed without any configuration: ordinary, non-access device services.
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
}

# Elevated services are allowlisted by entity, except the exact-pair policy
# domains below, which never accept entity-only authorization.
_ELEVATED: dict[str, frozenset] = {
    "switch": frozenset({"turn_on", "turn_off", "toggle"}),
    "input_boolean": frozenset({"turn_on", "turn_off", "toggle"}),
    "lock": frozenset({"lock", "unlock", "open"}),
    "cover": frozenset({
        "open_cover", "close_cover", "stop_cover", "toggle",
        "set_cover_position"}),
    "alarm_control_panel": frozenset({
        "alarm_arm_home", "alarm_arm_away", "alarm_arm_night",
        "alarm_arm_vacation", "alarm_arm_custom_bypass",
        "alarm_disarm", "alarm_trigger"}),
    "siren": frozenset({"turn_on", "turn_off", "toggle"}),
    "valve": frozenset({"open_valve", "close_valve", "set_valve_position"}),
    "camera": frozenset({"turn_on", "turn_off"}),
}

_EXACT_SERVICE_POLICY_DOMAINS = frozenset({
    "switch", "input_boolean", "lock", "cover", "alarm_control_panel",
})

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


def notification_service_permitted(service: str) -> bool:
    """Authorize reviewed output endpoints, not selectors or discovered names."""
    return (isinstance(service, str)
            and service not in ("notify.notify", "notify.send_message")
            and service in _validated_list(NOTIFICATION_ALLOWLIST_KEY, _NOTIFY_RE))


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
            if (entity_domain not in _EXACT_SERVICE_POLICY_DOMAINS
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
    """Permit only HA Assist API tools that cannot dispatch a service.

    The built-in control tools can resolve names and expand targets internally,
    bypassing JARVIS's exact entity/service authorization at dispatch.
    """
    return isinstance(tool_name, str) and tool_name in HA_READ_ONLY_TOOLS


def authorize(hass, domain: Any, service: Any, data: Any,
              entity_id: Optional[str] = None) -> tuple[bool, str]:
    """Return ``(allowed, reason)``. Deterministic, fail closed."""
    from .grounded_boundary import is_grounded, deny_action
    if is_grounded():
        return False, deny_action()
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

        if domain in _EXACT_SERVICE_POLICY_DOMAINS:
            if _service_permitted(target, domain, service):
                return True, ""
            return False, (f"{domain}.{service} on {target} requires an exact "
                           f"entity/service pair in {SERVICE_ALLOWLIST_KEY}")

        if service in base:
            return True, ""

        if target in allowlist():
            return True, ""
        return False, (f"{domain}.{service} on {target} requires the entity to "
                       f"be listed in {ALLOWLIST_KEY}")
    except Exception as exc:   # pragma: no cover - defensive, fail closed
        return False, f"authorization error: {exc}"
