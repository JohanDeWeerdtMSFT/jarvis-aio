# Home Assistant dispatch inventory

This inventory covers direct `hass.services.async_call` sites in the integration and both indirect Home Assistant Assist API dispatch sites. The direct-call gate is `scripts/kernel_bypass_check.py`; it enumerates every direct service call and fails CI for a world-mutating call outside the actuator seam unless the exact site is classified. It uses UTF-8 source reads and excludes the pure `kernel` modules by path.

## Direct service calls

| Site | Service | Classification and boundary |
| --- | --- | --- |
| `__init__.py:async_setup_entry` | `persistent_notification.create` | Startup warning when configuration recovery used defaults; notification, not device actuation. |
| `__init__.py:_jarvis_backup` | `persistent_notification.create` | Reports completion of the explicit backup service. |
| `__init__.py:_jarvis_restore` | `persistent_notification.create` | Reports completion of the explicit restore service. |
| `actuation.py:guarded_call` | Dynamic `(domain, service)` | Sole direct device-actuation call. `actuation_gate.authorize` checks the final concrete entity/service pair; planner, journal, event and verification behavior stay in the actuator seam. The bypass gate permits this function only. |
| `agent.py:_exec_weather_forecast` | `weather.get_forecasts` (two sites) | Read-only forecast request and a daily-forecast fallback. |
| `cognitive_core.py:_notify_all_devices` | `persistent_notification.create` | User-visible notification for a confirmed intrusion; device actions are handled separately. |
| `continued_conversation.py:_reopen_after_speaker` | `assist_satellite.start_conversation` | Reopens the selected voice satellite after playback; voice-session control, not home-device control. |
| `observer.py:_speak` | `tts.speak` | TTS output to selected media players; communication output, not a general media-control path. |
| `output_dispatch.py:_dispatch` | Dynamic `notify.<service>` | Validates payload and destination against the notification service policy, awaits the result and reports failures. Endpoint/privacy policy remains distinct from actuator authorization. |
| `proactive_audio.py:_speak_tts` | `tts.speak` (two sites) | TTS announcement with a fallback retry without optional voice settings. |
| `proactive_audio.py:_run_audit` | `jarvis.speak` | Fixed JARVIS speech service for infrastructure-audit announcements. |
| `tts_helper.py:async_announce` | `tts.speak` (two sites) | TTS batch call and per-speaker/voice-option fallback. |
| `voice_confirm.py:_confirm_native` | `assist_satellite.ask_question` | Native yes/no confirmation prompt; does not itself execute the requested action. |
| `voice_confirm.py:_start_listening` | `assist_satellite.start_conversation` | Opens the selected satellite microphone for a bounded follow-up. |
| `voice_confirm.py:ask_followup` | `assist_satellite.start_conversation` | Starts a follow-up turn or uses the bounded TTS/listen fallback. |
| `voice_confirm.py:announce_test` | `assist_satellite.announce` | Explicit diagnostic voice-output test. |

The table has 19 direct call sites. Communication and read-only classifications mean “not a general device actuator”; they do not replace destination validation, privacy review, or honest error handling. Adding a direct service call requires updating the classifier and this table in the same change.

## Indirect HA Assist API tools

| Site | Boundary |
| --- | --- |
| `agent.py:_execute_tool` | Only names in `HA_READ_ONLY_TOOLS` are permitted before calling `hass_api.async_call_tool`. |
| `conversation.py:JarvisAgent._agentic_loop` | Advertises and rechecks only the same read-only tool set before calling `hass_api.async_call_tool`; the loop also uses the read-only reasoning boundary. |

HA API control tools can resolve friendly names and expand area/device targets internally, outside JARVIS's final service gate. Therefore they remain denied in every scope. The legacy `ha_api_tool_allowlist` configuration key cannot grant access; custom action requests must use a JARVIS route that resolves a concrete entity and reaches the actuator seam.

## Target resolution, validation and rollback

The gate accepts a single concrete `entity_id` and rejects lists, `all`, comma-separated IDs, domain mismatches, and `area_id`, `device_id`, `floor_id`, `label_id` or `target` selectors. The deterministic local engine may resolve a single learned alias or an explicit local area request to concrete entity IDs; each resulting action is rechecked separately at the seam. A Home Assistant area/name selector is never passed through the built-in Assist API control tools.

Run `python scripts/kernel_bypass_check.py --check` and the focused authorization/provenance tests before merging. Reverting the read-only Assist API restriction reopens a tool-level control route that bypasses exact entity/service authorization; do not roll it back until an equivalent dispatch-time authorization boundary is implemented and tested.

This source inventory is not live-home acceptance. It does not establish downstream automation safety, physical-device behavior, notification privacy, or coverage of third-party Python code that dispatches through other APIs. Those limitations remain tracked in issue #4.