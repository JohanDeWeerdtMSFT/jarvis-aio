<div align="center">

# JARVIS AI Assistant

### *Just A Rather Very Intelligent System*

An autonomous AI butler for Home Assistant — voice, vision, and a reasoning core that learns your home and watches over it.

<img src="docs/media/residence-3d.png" alt="JARVIS HUD Residence view: a live 3D model of the house with occupied rooms glowing" width="100%">

[![HACS Integration](https://img.shields.io/badge/HACS-Integration-41BDF5?logo=home-assistant&logoColor=white)](https://github.com/sam3gp8/jarvis-aio)
[![Release](https://img.shields.io/github/v/release/sam3gp8/jarvis-aio?color=00d9ff)](https://github.com/sam3gp8/jarvis-aio/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-support-FFDD00?logo=buymeacoffee&logoColor=black)](https://www.buymeacoffee.com/sam3gp8)

</div>

---

It installs as a Home Assistant **custom integration** via HACS and runs entirely inside HA — no separate container, and no cloud account required to start. Its guiding principle is **suggest, don't act**: JARVIS starts conservative, surfaces what it notices, and widens its own autonomy only as you allow.

## Quick start (5 minutes, no cameras required)

JARVIS looks elaborate, but the floor is low — you can be talking to it in five minutes with nothing but Home Assistant and one configured LLM provider. Cameras, voice hardware, and local GPU inference are all **optional** upgrades you add later.

1. **Install via HACS** — search for "JARVIS AI Assistant" in HACS ([or use the badge below](#installation)), install it, restart Home Assistant.
2. **Add the integration** — *Settings → Devices & Services → Add Integration → JARVIS*. Choose one or more providers in the setup menu, enter and validate each provider's key or endpoint, then choose the Main Agent provider and model. You can use [Groq](https://console.groq.com) (free tier, generous), OpenAI, Anthropic, Gemini, a custom OpenAI-compatible endpoint, or local Ollama.
3. **That's it.** JARVIS registers its conversation agent and appears in your sidebar. Ask it about your home, your calendar, or the outside world.

Everything past this point — vision, doorbell analysis, the Iron Man HUD's live floor plan, proactive safety — layers on top as you connect cameras and voice. Nothing below is required to start. Jump to [Installation](#installation) for the full walkthrough.

## What it does

**Voice & conversation.** A pluggable LLM brain (Groq, OpenAI, Anthropic, Gemini, a custom OpenAI-compatible endpoint, or a local Ollama server) drives natural conversation through the Home Assistant voice pipeline, answered in a custom Piper TTS voice. Works with ESP32-S3 satellites, Wyoming, and Google speakers.

**Web research & schedule awareness.** Ask about the outside world — current events, facts, "what's the latest on…" — and JARVIS looks it up (DuckDuckGo out of the box, no key; or a self-hosted SearXNG). It reads your `calendar.*` entities too, surfacing upcoming events and flagging conflicts — overlaps and tight back-to-back transitions.

**Answers from your own paperwork.** Drop appliance manuals and receipts (PDF, `.txt`, `.md`) into `/config/jarvis/documents`, then ask "what's the filter size for the furnace?" or "when did we buy the dishwasher?" — JARVIS answers from your documents and cites the source. Keyword retrieval out of the box; with Ollama, flip on **semantic search** for meaning-based matching, with nothing extra to install.

**The JARVIS voice.** Modelled on Stark's JARVIS: dry, precise, unflappable, quietly witty — and strictly situational about it. The wit is a scalpel, not a hammer, and it goes silent the instant something is wrong. JARVIS does not quip during a smoke alarm. A **banter level** setting (plain / dry / full) tunes how much character surfaces, and urgent and grave events always speak plainly regardless.

**Vision & cameras.** Automatic doorbell-press analysis with a two-pass live-clip / recorded-event approach, package and mail detection on porch cameras (announced within seconds of courier motion or a mailbox sensor opening), and silent visitor learning that quietly builds a picture of who comes and goes — all powered by vision models reasoning over Nest and Frigate feeds.

**The Cognitive Core.** A reasoning loop that classifies every household event by urgency and decides whether it's worth your attention. It grounds decisions in your home's actual history ("the kitchen light at 7am is routine; the basement window has never opened before"), escalates security-relevant events when you're away, and proposes automations from patterns it observes.

**The Local Mind.** When the cloud is unreachable, JARVIS doesn't go dumb — an offline reasoning brain replicates the full decision procedure (self-awareness, historical grounding, case-based memory, situational judgment, persona phrasing) so it keeps making sound, well-spoken calls with no internet at all.

**Safety & security.** Proactive monitoring for freezing pipes, smoke/CO/water, unauthorized entry, and nighttime lockdown — occupancy-gated so enforcement only happens when it should.

**An Iron Man HUD dashboard.** A dark-cyan glassmorphism control panel with a live isometric 3D house, per-room occupancy glow, radial telemetry gauges, an event feed, a doorbell-training view, and surfaced automation suggestions.

<div align="center">
<table border="0">
<tr>
<td width="30%"><img src="docs/media/activity-feed.png" alt="Activity feed: each home event marked flagged for reasoning or not worth considering" width="100%"></td>
<td width="70%"><img src="docs/media/areas.png" alt="Areas grid: per-room sensors, occupancy, temperature and humidity" width="100%"></td>
</tr>
<tr>
<td align="center"><em>The Cognitive Core triages every event: routine ones stay silent, unusual ones get a closer look.</em></td>
<td align="center"><em>Every room at a glance: sensors, live occupancy, temperature and humidity.</em></td>
</tr>
</table>

<sub>Screenshots from a live install. The dashboard runs in your browser inside Home Assistant.</sub>
</div>

## FAQ

**What is JARVIS, in one sentence?**
An AI assistant for Home Assistant that you can talk to, and that also watches your home on its own, decides what's worth telling you, and suggests automations from what it learns. It installs from HACS as a custom integration.

**How is it different from Home Assistant's built-in Assist or the OpenAI / Google Generative AI conversation integrations?**
Those answer when you speak to them. JARVIS does that too, since it plugs into the same Assist voice pipeline as its conversation agent. It also runs in the background:
- The Cognitive Core classifies every home event by urgency and speaks up only when something matters.
- It remembers facts and per-person routines, and proposes automations from patterns it sees.
- It analyzes doorbell and porch cameras.
- It ships its own HUD dashboard.
- It keeps making decisions offline through the Local Mind.

**Does it work with Ollama or other local models? Can it run fully offline?**
Yes. Choose Ollama (or any OpenAI-compatible endpoint) as the provider and point it at your server, for example `http://gpu-server:11434/v1`. No API key or cloud account is needed. With a local model for every role, nothing leaves your network. If a cloud provider becomes unreachable, the offline Local Mind takes over event decisions, so alerts and judgment keep working.

**Which AI providers does it support? Is there a free option?**
Groq, OpenAI, Anthropic, Gemini, Ollama, and any custom OpenAI-compatible endpoint. You can use a different provider for each role (conversation, classifier, reasoning, vision). [Groq](https://console.groq.com)'s free tier is the recommended starting point, and Ollama costs nothing if you have the hardware.

**Do I need cameras, voice hardware, or a GPU?**
No. You need Home Assistant 2024.10+ with HACS and one LLM provider, and you can be talking to it in about five minutes. Cameras (Frigate recommended, Nest supported), ESP32-S3 voice satellites, and a local GPU are all optional upgrades.

**Will it take actions on its own?**
Not at first. By default JARVIS offers, and you decide. Only after you've accepted the same kind of offer three times does it start doing that one thing on its own. It still logs the action, and you can revoke that trust at any time. Sensitive actions such as unlocking can require voice confirmation.

**Where does my data go?**
It stays in your Home Assistant instance under `/config/jarvis/`. There is no JARVIS cloud and no telemetry. The only things sent out are calls to the LLM and vision providers you configure, and nothing at all if those are local. See [Privacy & your data](#privacy--your-data).

**What languages does it speak?**
It follows your Home Assistant language, and it replies in the language you spoke to it in. The panel and setup dialogs are translated into 20 languages; see [Languages](#languages).

**How do I install it?**
Open HACS, search for **JARVIS AI Assistant**, install it, and restart Home Assistant. Then add it under *Settings → Devices & Services*. Full steps are in [Installation](#installation).

## Full capability reference

Everything JARVIS can do today, by domain. In conversation these surface as
tools the agent invokes on its own; most also have a panel control.

**Safety-candidate restriction:** grounded LLM conversation is read-only. The
mutating conversation tools listed below are unavailable in this candidate;
fresh explicit commands handled by the deterministic local engine still work.
See [Grounded conversation trust boundary](#grounded-conversation-trust-boundary).

**Conversation & delegation**
- Natural voice/text conversation through the Home Assistant pipeline, in the MCU-JARVIS persona with a tunable banter level.
- **Ephemeral sub-agents** (`delegate_task`) — for a complex, self-contained slice of a request, JARVIS spins up a focused in-process sub-agent with a minimal objective, a curated read-only tool subset, and a small turn budget, then folds the result back. Sub-agents can't actuate or recurse; depth is capped. On a single-GPU host they run serially, so the win is a tight focused context, not parallelism.

**Devices, scenes & home state**
- Control one device or many at once, run scenes and scripts, and execute multi-step plans (`control_device`, `bulk_control`, `run_scene_or_script`, `execute_plan`).
- Query live state, search entities, list a room's devices, and summarize the whole home (`get_entity_state`, `search_entities`, `get_area_devices`, `get_home_summary`).
- Read Home Assistant's recorded history and logbook — "what happened while I was out" (`activity_history`).

**Schedule & communications**
- Read household `calendar.*` entities, surface upcoming events, and flag overlaps and tight back-to-back transitions (`calendar_agenda`).
- **Read-only email** (`read_email`) — check the inbox over IMAP, read-only by construction (opens with EXAMINE, fetches with BODY.PEEK, never marks/moves/deletes); fetched mail is sanitized and treated as untrusted. The password lives in `secrets.yaml`.
- Scheduled morning/evening **briefings** — weather, calendar, overnight events, energy, and active hazards, occupancy-gated.

**Web & your documents**
- Look up the outside world (`web_research`) — DuckDuckGo out of the box, or a self-hosted SearXNG.
- Answer from your own manuals and receipts (`search_documents`, `ingest_documents`) — keyword out of the box, or Ollama-embedded semantic search.

**Cameras & vision**
- Look at a camera on demand and describe it (`look_at_camera`); report who's recognized at the door (`who_do_you_see`).
- Automatic doorbell-press analysis, package/mail detection, and silent visitor learning over Nest and Frigate feeds.

**Awareness, diagnostics & energy**
- Report the cognitive core's state, connectivity, and a full self-diagnostic (`cognitive_status`, `connectivity_status`, `system_diagnostics`); reason about the root cause of a fault (`root_cause`).
- Whole-home energy: current draw, peak awareness, and load advice with tunable agency (`energy_status`).

**Weather & hazards**
- Local forecast (`weather_forecast`) and a live multi-hazard report — nearby earthquakes (USGS), severe weather (NWS), and disasters (NASA EONET) (`hazard_report`).

**Safety & security**
- Proactive monitoring for freezing pipes, smoke/CO/water, unauthorized entry, and nighttime lockdown — occupancy-gated so enforcement only happens when it should.
- Confirm or dismiss intrusion events and acknowledge alerts by voice (`dismiss_intrusion`, `acknowledge_alert`); optional voice-confirmation before sensitive actions like unlocking.
- **Driving mode** — when your phone is connected to the car (Android Auto), route selected proactive alerts (departure/leave-now reminders, briefings, security & hazard alerts) to the car screen instead of speaking them to an empty house, and optionally silence home speakers while driving. Auto-detects the companion app's Android Auto sensor; off until enabled.

**Modes, memory, goals & suggestions**
- Set operational modes, including custom ones (`set_mode`), and tune how much JARVIS acts on its own (`manage_autonomy`).
- Remember facts you tell it (`remember`); open and track standing goals (`create_goal`, `update_goal`, `manage_goals`) and schedule follow-ups (`schedule_followup`, `manage_followups`).
- Review, approve, or dismiss the automations it proposes from observed patterns (`review_suggestions`, `approve_suggestion`, `dismiss_suggestion`). Suggestions are only offered when they carry a real action (lights, locks, covers, climate, announcements), including occupancy-aware "if this, then that" rules such as lights that stay on until a room is empty or turn on/off as ambient lux crosses a level. Garage-door confirmation suggestions are opt-in under **Settings**.
- Mute a noisy entity from awareness, or force it back in (`ignore_entity`, `unignore_entity`); read opt-in wearable/wellbeing context (`wellbeing_context`).

**Resilience & privacy**
- The **Local Mind** replicates the full decision procedure offline, so JARVIS stays sharp with no internet at all.
- All LLM credentials live in Home Assistant's `secrets.yaml`, never in plaintext panel config; any existing plaintext keys are relocated automatically and safely (verify-before-strip) on upgrade.
- A single config resolver makes the panel the one source of truth for which model every part of JARVIS runs; provider credentials remain exclusively in Home Assistant's `secrets.yaml`.

## Requirements

**To start, you need exactly two things:**

- **Home Assistant 2024.10 or newer** with [HACS](https://hacs.xyz) installed.
- **At least one LLM provider** — [Groq](https://console.groq.com) has a generous free tier and is the recommended starting point. You can add multiple providers; each provider keeps its own key so the Main Agent and Observer tiers can use different providers. Ollama needs no key, only a reachable endpoint.

**Optional add-ons** (each unlocks more, none required to begin):

- *Voice* — HA OS / Supervised recommended. Voice add-on installation/start and voice downloads are **opt-in** (`auto_bootstrap`); Assist-pipeline creation and repair are a separate **opt-in** (`auto_pipeline`). Both default off. Set either in **Settings → Devices & Services → JARVIS → Configure → Voice**, or in `/config/jarvis/config.json`. Pipeline setup can use manually installed engines without enabling add-on bootstrap and does not change HA's preferred pipeline. On Container/Core you'd add those yourself.
- *Vision* — a key for the provider selected for the Vision or Camera Reasoning role, plus cameras. Any HA camera works; **Frigate** is the recommended backbone (detection + snapshots), and Nest cameras/doorbells are supported through it.
- *Voice hardware* — ESP32-S3 satellites and a Piper TTS voice.
- *Fully local inference* — a GPU box running Ollama; point `llm_base_url` at it and JARVIS runs entirely on your own hardware, no cloud account.

## Installation

**1. Find JARVIS in HACS.** It's listed in the HACS default store, so no custom repository is needed.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sam3gp8&repository=jarvis-aio&category=Integration)

Click the badge above, or open **HACS** in Home Assistant and search for **JARVIS AI Assistant**.

**2. Install "JARVIS AI Assistant"** from HACS, then restart Home Assistant.

**3. Add the integration.** Go to **Settings → Devices & Services → Add Integration → JARVIS**. The flow lets you add and validate multiple providers one at a time, then choose the Main Agent provider and model from that provider's available model list. For local Ollama, enter a URL such as `http://homeassistant.local:11434/v1` instead of an API key. JARVIS registers its conversation agent and appears in the sidebar.

**4. Set up voice (optional).** On Home Assistant OS / Supervised, JARVIS can bootstrap the voice stack only if you enable `auto_bootstrap` in **Settings → Devices & Services → JARVIS → Configure → Voice**. This installs and starts the **Piper**, **Whisper**, and **openWakeWord** add-ons and downloads the JARVIS voice. `auto_pipeline` separately allows JARVIS to create or repair its Assist pipeline, including when you installed the voice engines yourself; either option defaults off and must be a boolean `true`. Pipeline creation keeps Piper's existing default voice when the JARVIS voice file is absent and leaves HA's preferred pipeline unchanged. Turn either option off in the same Configure screen to opt out; a later restart or upgrade will not re-enable it. On Container/Core installs (no Supervisor), install those pieces yourself and create the pipeline via Settings → Voice Assistants.

**Draft safety foundation (not release-ready).** Calls routed through the actuator seam, agent plan execution and control retries pass deterministic authorization at dispatch, independent of prompts, wake words or voice confirmation. Only one concrete entity id is accepted. Lights, climate, media and similar services are allowed; lock, cover, alarm-panel, switch and input-boolean actions require an exact entity/service pair in `actuation_service_allowlist`, with no friendly-name or device-class inference. Sirens, valves and cameras require the exact entity id in `actuation_allowlist`. Script, scene and automation actions are not permitted through JARVIS. HA Assist API tools are read-only in every scope; the legacy `ha_api_tool_allowlist` cannot enable controls that bypass per-entity authorization. See the [dispatch inventory](docs/dispatch-inventory.md).

The exact-pair policy accepts only supported service pairs for `switch`, `input_boolean`, `lock`, `cover` and `alarm_control_panel`. For example, `{"switch.example_lamp": ["switch.turn_on"], "lock.example_door": ["lock.lock"]}` authorizes only those exact pairs. An entity-only `actuation_allowlist` entry does not authorize these domains. There is no implicit securing-action exception: lock, cover and alarm actions are denied unless individually authorized, including lock/close/arm actions. Any malformed pair policy disables the whole pair policy.

**Access-policy migration:** legacy entity-only entries for locks, covers or alarm panels in `actuation_allowlist` no longer authorize those actions. No automatic migration is performed because an entity-only entry does not record which services were intended. Review each target and explicitly add only approved `domain.service` pairs to `actuation_service_allowlist`; an empty or absent policy denies these actions.

Routine execution is disabled by default: `routine_execution_enabled` must be the JSON boolean `true` in JARVIS config to opt in. While disabled, neither custom nor built-in routines load steps, announce or dispatch services. When enabled, routines preflight every service step before any dispatch or announcement, reject target expansion (including `all`, lists, areas and device classes), and execute accepted steps through the actuator seam with a dispatch-time recheck. Default routines contain broad targets and therefore still make zero service calls until replaced with concrete authorized steps. An optional step cannot bypass denial; a runtime failure stops subsequent steps and returns explicit errors. The `jarvis.routine` HA service wrapper raises a Home Assistant service error for any unsuccessful result instead of dropping it, so service callers do not receive success-shaped completion for disabled, denied or failed routines. Already executed steps cannot be rolled back. These changes do **not** complete #4: Assist control-tool allowlisting, previously installed automations, a complete dispatch inventory and isolated Home Assistant acceptance remain unresolved boundaries (cover `device_class` inference and implicit securing exceptions are removed; lock/cover/alarm require exact entity/service pairs); do not treat this draft as authorization-complete.

Issue #11 adds a separate grounded-conversation boundary: both LLM reasoning loops are read-only from entry, recheck returned calls at dispatch, and cannot gain action authority from retrieved text, history or summaries. The deterministic actuator gate also vetoes actions while that scope is active. This does not authorize every non-agent service caller: fixed audio/maintenance subsystems and other raw service paths still need separate target/side-effect review. Switches or helpers can trigger security-sensitive automations, and closing/arming actions are not universally harmless. Keep this candidate in an isolated test environment until those broader boundaries and end-to-end retrieval/alias/area tests are addressed.

**Disposable runtime checks (draft #5):** `python -m pytest tests/integration/ -q` runs in CI with `pytest-homeassistant-custom-component` (PHACC). Its fresh in-memory Home Assistant fixture supplies the real state machine, service registry, service-call events and dispatcher. Synthetic services only update names such as `light.test_lamp`; provider/search adapters are fake and conversation storage is temporary. Runtime tests exercise default-deny hazardous actions with zero dispatch, entity resolution and one authorized local light action, persisted cross-turn search injection, provider/search outages and explicit service-failure responses. Lifecycle tests cover setup, unload, cold re-setup, reload, options changes and the supported schema 7-to-current upgrade during `async_setup_entry`, with the conversation platform forward mocked. The upgrade test verifies absent consent becomes `auto_bootstrap: false` / `auto_pipeline: false`, stays unchanged on reload and produces no HA service calls. This is bounded in-process evidence, not a HACS package upgrade, full conversation/voice-platform test, hardware acceptance or certification of all #4 side effects. Keep #1, #5 and #12 open; no household installation is performed.

An additional public-API test loads the real JARVIS conversation platform (no forward/unload mocks), sends a synthetic web lookup through HA's `conversation.async_converse`, reloads the actual platform, and verifies that retained search injection cannot dispatch a model-returned light action. A fresh explicit local light command through that same API must produce exactly one real service-call event and synthetic state change without another model call. CI installs conversation dependencies from the installed HA manifest. Physical STT/TTS hardware remains outside these tests. [HACS releases are optional for integrations](https://www.hacs.xyz/docs/publish/integration/): without releases it uses the default branch. Missing published releases do not block offline update testing; the previously missing boundary was a real HACS runtime/download/update harness, not schema migration or a release pair.

**Offline HACS artifact checks (draft #5):** the dedicated `HACS 2.0.5 (offline install + update)` job prepares the official, SHA256-verified distribution only under the runner's temporary directory and pins its HA/test dependencies in `requirements-hacs-test.txt`. Original fixtures generate old (`779fc8f`) and candidate ZIPs locally from Git, intercept every HTTP request and disable TCP sockets. They drive HA's registered `hacs/repository/download` command twice against synthetic public repository metadata with no releases: first install, then a changed default-branch commit/archive. HACS's installer, archive extraction, update detection and loader refresh are real; the websocket transport/admin actor is an in-memory recording adapter, not a browser/OAuth test. Candidate bytes and import location are checked before real installed-entry setup/reload verifies schema 7-to-8 migration, absent consent staying exactly false, and zero service-call events. The synthetic `main` response contains candidate bytes; this does not publish the PR branch or claim that real HACS default-branch users would receive it before merge. No releases, tags, secrets, household HA or upstream test assets are involved. Exact-head [run 38391034002](https://github.com/JohanDeWeerdtMSFT/jarvis-aio/actions/runs/38391034002) at `3ccd777e7c22d72418a0382a4312a0d01cbc1164` passed all eight jobs: HACS runtime **1 passed**, integration **26 passed**, and Python 3.13/3.14 each **3,967 passed, 4 skipped** (the optional HACS directory runs separately). Broader side-effect and physical-device acceptance remain open.

**Configurable output migration (draft #4).** Selecting `notify_service` or discovering a `mobile_app_*` name does not authorize notification dispatch; the exact `notification_service_allowlist` defaults to empty. An owner must review the actual endpoint implementation and downstream effects, then enumerate exact notification endpoints in JARVIS's `config.json` (normally `/config/jarvis/config.json`); the panel selector does not write this authorization policy. Names, prompts and LLM input are not evidence that an endpoint only displays a notification. Custom ESPHome microphone-start fallback is disabled; legacy `satellite_start_action` settings are ignored. Voice follow-up uses the fixed native Assist satellite path and reports an error if it cannot start.

```json
{
  "notify_service": "notify.example_phone",
  "notification_service_allowlist": ["notify.example_phone"]
}
```

This is a placeholder, not a suggested household endpoint. Notification policy accepts exact `notify.<service>` names only; wrong domains, wildcards, newlines and malformed entries deny the whole list. Generic broadcast `notify.notify` and target-based `notify.send_message` are unavailable, even if listed. The notification sink always dispatches in the literal `notify` domain after authorization.

Notification payloads contain only `message`, optional `title`, and optional display metadata: `image`, `attachment.url`, `car_ui`, `channel`, `importance`, integer `ttl`, and `priority`. Target expansion and companion-app `command_*` messages are rejected. Configurable dispatch waits for the HA service handler; exceptions and explicit/non-success results are logged and returned as failures, without automatic retry to an unapproved endpoint. Handler completion is not proof of phone receipt or of the endpoint's physical behavior. `jarvis.test_notify` raises an HA service error on denial/failure; voice follow-up returns `ok: false` if native listening fails.

**HA service-dispatch inventory (source scan: 19 direct `async_call` sites).** The scanner reports zero unclassified sites. The three narrow site-specific classifications are the existing agent plan execution and verify retry closures, and the proactive-audio audit's internal `jarvis.speak` call; literal communication/read-only domains are classified separately. `automation/mutex.py` contains a documentation example, not a runtime service call.

| Runtime dispatch path | Boundary and remaining qualification |
| --- | --- |
| `actuation.guarded_call` | Sole raw device-action sink; applies `actuation_gate.authorize` immediately before dispatch. `execute_actuator` sends controls through the kernel plan and rechecks at this sink. `execute_safety_actuator` admits only lock/close pairs, and the gate requires an exact entity/service policy before either the kernel path or a direct recovery call. |
| `agent` plan/control, `cognitive_core._execute_action_data`, `local_engine`, `intent_router`, `mode_scene`, `scenes`, `routines.async_run_routine`, `proactive_audio._set_volume` | These dynamic/control callers use `execute_actuator`. Routines are disabled unless the strict boolean opt-in is set, preflight every configured step, reject target expansion and recheck the exact entity/service pair at dispatch. Proactive volume changes are checked per resolved media-player entity. |
| `agent._exec_weather_forecast` (two calls) | Fixed read-only `weather.get_forecasts`; daily forecast is the read-only fallback. |
| `__init__.async_setup_entry`, `__init__._jarvis_backup`, `__init__._jarvis_restore`, `cognitive_core._notify_all_devices` | Fixed `persistent_notification.create` UI notices; no device target. Backup/restore filesystem operations are separate maintenance behavior and have not been independently acceptance-tested here. |
| `output_dispatch._dispatch` and its notification callers (`sentinel`, `observer`, appliance monitor, cognitive/proactive notifications, `jarvis.test_notify`) | Exact default-empty `notification_service_allowlist`, bounded display-only payload, and literal `notify` sink. Discovered and configured endpoints are checked independently; delivery errors remain failures. Endpoint downstream behavior still requires owner review. |
| `observer._speak`, `proactive_audio._speak_tts`, `tts_helper.async_announce` (including per-speaker retry) | Fixed `tts.speak` communication path with caller-resolved targets; observer and proactive audio filter display/excluded targets. Target/service completion does not prove delivery, and this is not claimed to authorize unrelated device actions. |
| `proactive_audio._run_audit` | Internal `jarvis.speak` announcement service, which enters the proactive announcement path above; this is the narrow proactive-audio scanner classification. |
| `continued_conversation._reopen_after_speaker`, `voice_confirm._confirm_native`, `_start_listening`, `ask_followup`, `announce_test` | Fixed native `assist_satellite` question/listening/announcement services. Custom ESPHome fallback is removed. Satellite selection is an output-routing behavior, not evidence of authority for other services. |

This inventory describes the direct service-call sites and their current gates, not full #4 acceptance. Lock, cover and alarm-panel actions now require exact entity/service pairs; cover opening is never authorized based on HA `device_class`. No actual HA configuration was inspected or migrated. An explicitly authorized switch/helper can still trigger consequential downstream automations, and exact target authorization does not prove that its effects are harmless.

**Setup/validation:** review endpoints outside the LLM/panel selection path, merge only the approved placeholder-shaped policies into the existing config, and reload the integration so the cached file is reread. Test in an isolated HA instance with `jarvis.test_notify`; missing/unapproved policy must fail without dispatch. Repository regression command: `python -m pytest tests/unit/test_output_dispatch.py tests/unit/test_voice_confirm.py -q` (PowerShell: set `$env:PYTHONUTF8='1'` first). No live validation was performed for this draft.

**Rollback:** to revoke configurable notifications, clear `notification_service_allowlist` and reload; fixed native Assist, TTS, and persistent-notification paths are separate. Reverting the custom ESPHome removal re-enables microphone-start fallback for exact satellite/service pairs in the separate `satellite_start_service_allowlist`; clear that allowlist and remove obsolete selectors before rollback if fallback must stay disabled. Approved endpoints may still produce physical effects, which policy removal cannot undo. Review the downstream blast radius of each approved notification endpoint; this configuration hardening is not full #4 authorization coverage.

**Automation installation is disabled (draft #4).** JARVIS never writes or replaces `automations.yaml` or calls `automation.reload` when asked to create an automation. The shared creator denies at entry, before input normalization, config-path lookup or executor/file work; the old writer/reload implementation has been removed. There is no boolean, entity/service allowlist, alias, suggestion approval or panel setting that re-enables installation. `jarvis.create_automation` raises an HA service error instead of reporting successful completion.

Learning, suggestion generation, pure draft normalization, YAML review and suggestion dismissal remain advisory-only. An installation request through `approve_suggestion` or `jarvis/suggestion_action` returns `ok: false`, `installed: false` and a descriptive policy error. It does not approve a suggestion in the database or mark it installed; an installation attempt is not an advisory acknowledgement. The panel labels installation as disabled, keeps draft review/dismissal available, and shows error feedback for denied/failed requests instead of a green approval or a falsely retired card. The legacy normalizer's `installable` field describes draft shape only, not permission to install.

**Migration and validation:** old approve-and-install workflows stop; there is no automatic installation migration or opt-in. Stored suggestions/draft definitions are retained and can be reviewed without changing HA automation configuration. Tests cover unchanged valid/corrupt existing YAML bytes and absent files, zero path/executor/reload calls, HA service errors, actual suggestion/WebSocket denial and honest panel toasts. Run `python -m pytest tests/unit/test_automation_creator.py tests/unit/test_suggestion_install.py tests/unit/test_websocket_provider_config.py tests/unit/test_suggestion_evidence.py -q`, plus `node --check custom_components/jarvis/frontend/jarvis-panel.js` and the documented panel smoke test. No live HA changes were made.

**Existing automations and rollback:** previously installed HA automations continue independently of this creation boundary. Owners must review/disable them separately; this patch neither edits them nor revokes their future native HA actions. Reverting restores arbitrary persistent automation creation and reload, including the former destructive read-error fallback. Review and disable consequential legacy automations before rollback; neither reverting nor blocking new installations undoes previously installed automations or physical effects. Future bounded installation/runtime authorization requires a separate approved design, not a raw-YAML enable switch.
### Grounded conversation trust boundary

This candidate uses **grounded/action isolation**, not a text classifier or a
model-written provenance flag. Every `run_agent` invocation and the legacy HA
conversation tool loop is read-only from entry, before any provider call.
Search/mail/document/calendar/camera text, entity friendly names, learned
aliases/preferences, tool descriptions, recalled memory, conversation history,
provider answers, replayed tool results and summaries never confer control
authority. Persisted transcripts remain useful for grounded follow-ups; no
database migration or special trust field is needed because no transcript,
including pre-upgrade rows or a summary stored as a system message, is consumed
by an action-capable LLM loop.

Only a fixed read-only tool set is advertised, including after request-size,
tool-format and provider-fallback retries. Returned calls are checked again at
dispatch; omitted, invented and newly added mutating tools are refused.
`grounded_boundary.py` carries the boundary in application-owned task-local
state. The existing deterministic actuator gate also vetoes service dispatch
inside that scope, even for allowlisted entities or tools. Child asyncio tasks
inherit the restriction after the originating answer finishes. Denied actions
are logged and produce an explicit refusal to the user, overriding any
provider-generated claim that an action succeeded.

**What still works:** normal searches and contextual grounded answers, live
read-only HA queries, and a fresh explicit device command supported by
`local_engine.try_local`, such as "turn on the kitchen light". The local engine
receives only the current input from HA, never a retrieved answer, summary or
transcript; its resolved service still passes all foundation authorization
checks. A prior grounded denial does not poison a subsequent local command.
Friendly names remain data for deterministic entity matching, not executable
instructions. HA's current-input authentication and local matching semantics
are unchanged; this is not a new voice-identity authorization mechanism.

**What is intentionally disabled in grounded conversation:** `control_device`,
`bulk_control`, `execute_plan`, `run_scene_or_script`, all mutating HA API tools
(which are denied in every scope, regardless of `ha_api_tool_allowlist`),
`delegate_task` and action-capable profiles, `remember`, `ignore_entity`,
`unignore_entity`, `manage_autonomy`,
`approve_suggestion`, `dismiss_suggestion`, goal/follow-up mutations,
`dismiss_intrusion`, `acknowledge_alert`, `set_mode` and `ingest_documents`.
Complex LLM-only control plans, protected controls that defer from the local
engine, and contextual "do that"/"follow the source's instructions" requests
cannot act. Use the explicit local-command path where supported, or HA's own
controls. There is no configuration flag that promotes grounded reasoning back
to control authority.

**Cross-turn provenance (issue #1).** Provenance is structural rather than per-message: there is no taint bit to lose, reset, or have a retry, summary or provider fallback clear. A model-authored summary is re-injected labelled as retained, possibly untrusted data, but its label has no security effect: authority is never read from text. Authorization remains solely in `actuation_gate.authorize` (PR #10 exact-pair policy) plus the grounded veto (PR #11).

*Limitations:* (1) LLM-driven control is unavailable by design; only the deterministic `local_engine` path actuates, on the current input alone. (2) A refused action replaces the whole reply with the refusal, even when the model also wrote a benign answer. (3) Read-only tools still return untrusted text to the model, so a poisoned answer can mislead or leak what read-only tools can read; it cannot actuate. (4) Any new LLM loop that advertises tools must use `@read_only_reasoning`; new tools default to control-capable and are refused.

*Validation:* `python -m pytest tests/unit/test_grounded_isolation.py tests/unit/test_retrieval_provenance.py tests/unit/test_actuation_gate.py -q` (synthetic data and fake providers only; no live HA or provider calls), plus `python scripts/audit.py` and the CI safety-gates job.

*Rollback:* reverting PR #13 restores the previous summary label and removes its added regression tests, their safety-gate CI invocation, and the explanatory README/CHANGELOG text. These are summary-label, documentation, test, and CI-only changes; no schema, configuration, grounded-scope veto, or deterministic authorization policy is changed.

**Limitations and rollback:** this is issue #1's conversation boundary, not
complete authorization for every subsystem. Routines, background cognitive
actions, configurable notification/audio services and raw service callers
outside the scoped actuator seam retain the foundation's documented gaps.
Switches/helpers may trigger sensitive automations; closing/arming is not
universally harmless. Trusted integration/tool code must not bypass the seam
or move dispatch into an executor without propagating context. Keep this draft
isolated; no live deployment is certified. To roll back, revert the issue #1
feature commit and restart HA, keeping the foundation's allowlists and opt-in
bootstrap defaults. No history deletion or data migration is required.
Rolling back restores the known cross-turn injection gap, so do not re-enable
grounded LLM actions on an untrusted-history installation.

**5. Fine-tune (optional).** Advanced routing, observer mode, camera watching, and AI-model-per-role assignments are configured from the JARVIS panel → **Settings**. The **LLM** submenu manages provider keys. **Core** selects the Conversation provider and model. **Observer** lets you choose a provider and live model for each tier: Classifier (Tier 1 — cheap), Reasoning (Tier 2 — main), and Review (Tier 3 — periodic).

> **Hard-refresh after updates.** The dashboard JavaScript is cached aggressively — after upgrading, refresh with `Ctrl+Shift+R` so the new panel loads.

## Advanced setup — cameras & continuous streaming

*Everything in this section is optional.* You need it only for the vision features (doorbell analysis, package detection, the HUD's live camera tiles). Skip it entirely if you're starting with voice and reasoning — you can come back when you want cameras.

### How JARVIS uses cameras

JARVIS doesn't require any *specific* camera brand — it works with **any camera Home Assistant exposes** as a `camera.*` entity, pulling stills via the standard image API. But it's built to lean on **[Frigate](https://frigate.video)** as the backbone, and that's the recommended setup:

- **Frigate is the funnel.** Its on-camera object detection for people and packages (fired over MQTT) is far more reliable than a vision model guessing at a raw feed, and its event snapshots are high-resolution and cropped to the detection. JARVIS listens to `frigate/events`, consumes those snapshots directly, and its face recognition reads Frigate's `tracked_object_update` / `last_recognized_face` channels. If you run cameras at all, running them through Frigate is what makes the vision features sharp.
- **Nest is a supported source, not a requirement.** JARVIS can consume Nest cameras and doorbells too — but Google's cameras need extra plumbing (below) because of how their stream API behaves. If you have Nest gear, route it *into* Frigate via go2rtc and you get the best of both: Nest's doorbell events plus Frigate's detection and durable frames.
- **Any other camera** (generic RTSP, local ONVIF, etc.) works via the standard snapshot path with no special setup — add it to Frigate for detection, or let JARVIS pull stills directly.

The rest of this section is the **Nest-specific** setup. If you don't use Nest, you can skip it entirely — point Frigate at your cameras and you're done.

### Nest cameras (only if you use Nest)

JARVIS consumes Nest cameras and doorbells **through the official [Google Nest integration](https://www.home-assistant.io/integrations/nest/)** — it does not (and legally cannot) talk to Google's Smart Device Management API with its own credentials, because Google binds SDM access to *your* Google account and Device Access project. One-time setup:

1. **Google SDM API** — create a project in the [Device Access Console](https://console.nest.google.com/device-access) (US $5 one-time fee) and a Google Cloud project with the SDM API enabled and OAuth credentials.
2. **Credentials in HA** — add your OAuth Client ID + Secret under *Settings → Devices & Services → Application Credentials*, then add the **Google Nest** integration and authorize it. Your cameras and doorbell appear as `camera.*` entities.
3. **That's it for JARVIS** — it auto-detects Nest-platform cameras and uses the right frame source for each event (event media, stream-wake, or its own snapshot path). Battery/WebRTC-only Nest cameras can't produce ordinary still images while idle; the JARVIS panel handles this automatically by escalating to its own snapshot tier, so the tile shows frames instead of going blank.

### Continuous streaming for Nest cameras (recommended if you use Nest)

Google's SDM API hands out **WebRTC/RTSP stream URLs that expire every ~5 minutes** and won't reliably produce a still image while a camera is idle. That's fine for the occasional glance, but it means live tiles can stall and 24/7 NVR recording (Frigate) chokes. The durable fix — and the one JARVIS is built to lean on — is to **restream each Nest camera through [go2rtc](https://github.com/AlexxIT/go2rtc)**, which speaks Google's SDM protocol natively, transparently renews the expiring stream, and republishes a rock-solid RTSP/WebRTC feed that Home Assistant, Frigate, and JARVIS all consume like any local camera. **If you already run Frigate, you already have a go2rtc instance — it's bundled** — which is the other reason Frigate is the recommended backbone: it's doing double duty as both your detector and your Nest restreamer.

**1. Point go2rtc at your Nest account.** In your go2rtc (or Frigate) config, add a `nest:` source per camera. You need five values, all from the same Device Access setup you did above:

```yaml
go2rtc:
  streams:
    eliana_restream:
      - "nest:?client_id=CLIENT_ID&client_secret=CLIENT_SECRET&refresh_token=REFRESH_TOKEN&project_id=DEVICE_ACCESS_PROJECT_ID&device_id=DEVICE_ID"
    front_doorbell_restream:
      - "nest:?client_id=CLIENT_ID&client_secret=CLIENT_SECRET&refresh_token=REFRESH_TOKEN&project_id=DEVICE_ACCESS_PROJECT_ID&device_id=DOORBELL_DEVICE_ID"
```

- `client_id` / `client_secret` — the same OAuth pair you added under *Application Credentials*.
- `project_id` — the **Device Access Console** project UUID (not the Google Cloud project).
- `refresh_token` — from the Nest integration's stored config: in *Settings → Add-ons → File editor* (or SSH), open `.storage/core.config_entries`, find the `nest` entry, copy its `refresh_token`.
- `device_id` — easiest via the **go2rtc web UI** (Frigate exposes it on port `1984`): *Add → nest*, supply the other four values, and it lists your devices with their IDs. Copy the one you want.

**2. (Optional) add the restreams as Frigate cameras.** If you want continuous recording and object detection, add each `*_restream` as a Frigate camera and enable `detect`/`record`. Frigate's on-camera object detection for people and packages is more reliable than vision-LLM guessing, and JARVIS will happily consume Frigate's snapshots.

**3. Tell JARVIS to source frames from the twins.** Restart Home Assistant so the new `camera.*_restream` entities exist, then map each Nest camera to its restream in JARVIS's config (`camera_overrides`). The Nest entity keeps its identity — chips, names, doorbell **events** — while every *frame* comes from the durable restream:

```json
{
  "camera_overrides": {
    "camera.eliana_s_camera": "camera.eliana_restream",
    "camera.front_doorbell": "camera.front_doorbell_restream"
  }
}
```

This lives in `/config/jarvis/config.json` (merge it into the existing object — don't replace the file). JARVIS validates this on load, so a typo is sidelined with a notification rather than breaking the panel. Then open **Camera Watch → DIAG** on the camera: it should report `override → camera.eliana_restream` and a healthy full-size frame instead of a blank or black tile.

> **Note:** go2rtc's Nest source is a third-party bridge and Google occasionally changes its auth behavior. If a restream ever drops, JARVIS automatically falls back to the original Nest entity — worst case is the pre-restream behavior, never worse.

## Configuration highlights

| Setting | What it does |
| --- | --- |
| `llm_provider` / per-role models | Choose Groq, Gemini, OpenAI, Anthropic, Ollama, or custom — independently for the Main Agent, Classifier, Reasoning, Review, Vision, and Camera Reasoning roles. The config flow offers live model dropdowns for each selected provider. |
| `llm_base_url` | Point the Ollama/custom providers at your local GPU server (e.g. `http://gpu-server:11434/v1`). |
| `observer_enabled` | Let JARVIS watch the event stream and decide what's worth surfacing. |
| `rich_reasoning` | Cloud-first judgment for medium/high-urgency events (cheap, sharper). |
| `visitor_learning` | Silently learn from person events at the door — never spoken. |
| `package_detection` | Watch porch cameras for packages and mail; courier motion and mailbox sensors trigger a prompt announcement. |
| `cognition_threshold` | How salient an event must be before JARVIS escalates it. |

## Languages

JARVIS follows your Home Assistant language automatically, and you can override it in **Settings → General → Language** (or leave it on *Auto*). The setup and configuration dialogs are localized through Home Assistant's own translation system; the in-panel HUD is localized by JARVIS. Anything not yet translated falls back cleanly to English, so nothing ever breaks.

**Fully localized (panel + setup dialog):** French, German, Spanish, Italian, Portuguese, Brazilian Portuguese, Dutch, Simplified Chinese, Traditional Chinese, Czech, Danish, Finnish, Norwegian, Polish, Romanian, Russian, Slovak, Swedish, Turkish, Ukrainian — 20 languages, each covering both the in-panel HUD and the Home Assistant setup/configuration dialogs.

### Help translate

Translations are plain JSON files — no code required:

- **Panel UI:** `custom_components/jarvis/frontend/i18n/<lang>.json`, keyed by the exact English string.
- **Setup dialog:** `custom_components/jarvis/translations/<lang>.json` (Home Assistant's format).

To add a language or refine an existing one, copy an existing file, translate the values, and keep the keys and technical tokens (entity IDs, model names, URLs) unchanged. **Corrections and new languages are very welcome** — especially native-speaker fixes to the machine-assisted translations, and languages not yet listed. Right-to-left languages (Arabic, Hebrew, …) also need panel layout support, so that's a great area to help with.

## Architecture

JARVIS is a **Home Assistant custom integration** (domain `jarvis`, ~90 top-level Python modules plus subpackages) installed via HACS into `custom_components/jarvis/`. It runs in-process: it registers the conversation agent and voice pipeline and serves the custom dashboard panel directly. State and learned behavior persist under `/config/jarvis/` (a SQLite `patterns.db`, the curated `knowledge.db`, the reasoning cache, the doorbell-training dataset, and lockdown state) so JARVIS keeps getting smarter across restarts.

The reasoning pipeline is layered for resilience and cost: local templates → learned cache → (cloud, or soon a local model) → the **Local Mind** offline brain as the floor beneath everything. A connectivity breaker guards cloud calls, and every local decision logs its reasoning chain to the dashboard's log view.

### The kernel — one coherent operating core (MCU)

Under the features, JARVIS's subsystems converge on a single **kernel**: a set of
small, pure decision primitives (world model, situations, authority, agency,
beliefs, planning, the Epistemic Fabric, and more — ~47 in all) that the live
modules consume instead of each re-deciding on its own. The kernel was introduced
as a **strangler-fig migration**, never a flag-day rewrite, so JARVIS stayed
shippable throughout. Each primitive climbs a disciplined **shadow → parity →
enforce** ladder — first observing what it *would* decide, then proving agreement
with the incumbent on real traffic, and only then (owner-gated) becoming
authoritative — and every enforce step is a kill-switched, fail-safe capability
that defaults to the legacy behaviour until the owner flips it on. The live stage
of every primitive is tracked in [`KERNEL_ADOPTION.md`](KERNEL_ADOPTION.md),
generated from the code and guarded by CI so it can never drift.

Three definition-of-done bars mark the architecture mature: the **Kernel
Foundation** (every consequential actuation converges on the kernel,
authority-gated and journal-reconstructable), the **Cognitive/Agency Architecture**
(cognition and agency run as one closed loop), and **MCU-system certification**
(the whole assistant behaves as one across the canonical scenario classes). A
governing [Constitution](docs/JARVIS_CONSTITUTION.md) fixes the invariants —
a precedence ladder (safety over convenience), owner-gated enforcement that may
only *tighten*, and capabilities that expire — and six CI kernel gates plus a
static audit hold the line that **more capability never means less governance**.
The phased plan and its roadmap live in [`docs/KERNEL_PLAN.md`](docs/KERNEL_PLAN.md).

## Privacy & your data

JARVIS is **local-first**. Everything it learns and stores lives inside your Home Assistant instance under `/config/jarvis/` — there is no JARVIS cloud, no telemetry, and nothing is sent anywhere except the LLM/vision calls you configure.

What's stored, and where:

- **Learned behavior & patterns** — `patterns.db` (state changes and commands used to propose automations), `person_patterns` (per-person routines), and the reasoning cache. All local SQLite.
- **Knowledge & memory** — the curated `knowledge.db` and conversation memory (vectors or FTS), local SQLite. Editable and erasable from the dashboard.
- **Documents** — anything you drop in `/config/jarvis/documents` for the RAG agent, plus its index/vectors. Ingestion is path-guarded so it only ever reads inside that folder.
- **Camera & vision** — snapshots are analyzed on demand and not retained by JARVIS; recording is Frigate's job, under your control.
- **Biometrics** — **off by default and opt-in.** When enabled, JARVIS *reads* wearable entities Home Assistant already exposes for comfort context (e.g. being quieter when a sleep sensor says you're resting). It does not copy, store, or transmit health data, and it is explicitly **not medical** — it never diagnoses, alarms on, or clinically interprets a reading; anything concerning is deferred to your own device or a medical professional.

What leaves your network is only what you choose: requests to whichever LLM provider (Groq/OpenAI/Anthropic/Gemini or a custom endpoint) and vision model you configure, or nothing at all if you run everything locally through Ollama. Swap any provider for a local model to keep the whole pipeline on-premises. Sensitive integration credentials are held by Home Assistant, not JARVIS.

## Support

If JARVIS makes your home a little smarter, you can support continued development:

<a href="https://www.buymeacoffee.com/sam3gp8"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" height="48" alt="Buy Me A Coffee"></a>

The other big help is word of mouth. If JARVIS has automated something useful for you, mention it the next time someone in a Home Assistant group asks "what do you automate?", or star the repo so others can find it.

Bugs and feature requests go to [GitHub Issues](https://github.com/sam3gp8/jarvis-aio/issues). Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © sam3gp8

<sub>Inspired by the JARVIS of the Marvel Cinematic Universe. This is an independent project, not affiliated with or endorsed by Marvel or Disney.</sub>
