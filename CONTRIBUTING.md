# Contributing to JARVIS

Thanks for your interest in improving JARVIS. This document covers the repository
layout, the development workflow, and the release process.

## Repository layout

```
jarvis-aio/                         repo root (HACS integration repository)
├── hacs.json                        HACS metadata
├── README.md  CHANGELOG.md  LICENSE
├── icon.png  logo.png               branding (for home-assistant/brands)
├── .github/                         funding, issue templates, CI
├── scripts/bump_version.sh          one-command version bump
│   └── legacy_addon_bootstrap.py    reference for the in-progress in-integration bootstrap
└── custom_components/jarvis/        the integration (domain: jarvis)
    ├── manifest.json
    ├── __init__.py + 47 modules
    └── frontend/jarvis-panel.js     the dashboard
```

HACS installs `custom_components/jarvis/` into Home Assistant. The integration
runs in-process; the config flow (or a migrated legacy config) sets it up.

## Code standard

This project holds to senior+ engineering output:

- **4-pass audit before every release:** (1) syntax, (2) integration references,
  (3) all modules parse, (4) version bump + package.
- **Simulate tests internally** before shipping — the codebase carries standalone
  test harnesses for the reasoning loop, the Local Mind decision matrix, the
  package state machine, cognition salience tiering, and the speech composer.
- **Honest caveats** documented with every change. Verification before speculation.
- No careless mistakes, and no apologies in place of fixes.

## Local checks

These are the same checks the `Validate` CI workflow runs on every push:

```bash
# Full audit: bytecode compile + relative-import resolution + exported-name checks
python3 scripts/audit.py

# Unit tests
python3 -m pytest tests/ -q

# Dashboard JavaScript parses
node --check custom_components/jarvis/frontend/jarvis-panel.js

# Kernel adoption + behavioral coverage gates (no drift, no undeclared actuators)
python3 scripts/kernel_adoption.py --check
python3 scripts/kernel_coverage.py --check
```

## Kernel contract rule for new actions

**Any new behaviour that can cause a consequential action on the home — calling a
service, running a scene/script, applying a mode — must enter through the kernel
contract from the start and be a declared path in `_PATHS`
(`scripts/kernel_coverage.py`).** This is enforced: `kernel_coverage.py --check`
(a CI gate) fails if a tool in agent's `_TOOL_MAP` is neither a declared coverage
path nor in the `_NON_ACTUATOR_TOOLS` allowlist. When you add a tool that changes
the home, wire it onto the kernel contract (WorldModel read → ActuatorRequest /
ActuatorOutcome → actuation `JarvisEvent` → one-step `Plan`) and declare it as a
path; a read-only or bookkeeping tool goes in the allowlist with a one-line
rationale. See `KERNEL_COVERAGE.md` and `KERNEL_ADOPTION.md`.

## Versioning

JARVIS uses semantic versioning — `MAJOR.MINOR.PATCH` — and the digit is chosen by
the **nature** of the change, not its size:

- **PATCH** (`x.y.Z`) — a bug fix, or an internal / reliability change with no new
  user-facing capability. Most changes land here. A one-line fix is still a PATCH.
  _e.g._ `9.18.0` → `9.18.1`.
- **MINOR** (`x.Y.z`) — a new, backward-compatible user-facing capability (a new
  tool, panel feature, config option). A small-but-genuinely-new feature is a MINOR.
  _e.g._ `9.18.x` → `9.19.0`.
- **MAJOR** (`X.y.z`) — a breaking change to config, stored data, APIs, or behaviour
  users rely on. _e.g._ `9.x.x` → `10.0.0`.

A change that doesn't affect the shipped integration (contributor docs, CI, repo
meta) takes **no version bump** — `release.yml` only cuts a release when the
manifest version changes, so there's nothing to publish.

## Releasing

Bump the version everywhere it appears with one command:

```bash
./scripts/bump_version.sh 6.3.3
```

This updates the integration `manifest.json` (the source of truth) and the version
string in `jarvis-panel.js`. Then commit, tag (`git tag 6.3.3` — tags are `X.Y.Z`,
no `v` prefix), and push the tag — the validation workflow runs on every push, and
HACS publishes from the tag (no add-on/Docker build).

After updating on a live system, hard-refresh the browser (`Ctrl+Shift+R`) so the
cached dashboard JavaScript reloads.

## Pull requests

Keep changes focused, include a short rationale, and note any limitations. If a
change touches the reasoning pipeline, the camera/Nest paths, or cognition
salience, please describe how you verified it.
