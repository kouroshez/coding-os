---
id: TASK-971
title: "Ship the Hub SPA inside the wheel so a PyPI install renders the UI"
swimlane: infra
kind: bug
epic: null
labels: [packaging, hub, P0, ready]
status: complete
priority: P0
appetite: 1d
created: 2026-08-14
started: 2026-08-14
completed: 2026-08-14
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-971: Ship the Hub SPA inside the wheel so a PyPI install renders the UI

**Outcome (one sentence):** A wheel installed from PyPI into an empty venv serves the real Hub SPA at / instead of the "SPA not built yet" placeholder.

## Read First
- docs/engineering/hub-architecture.md
- pyproject.toml § tool.setuptools.exclude-package-data
- .github/workflows/release-please.yml

## Repro Steps
`uv build --wheel` then inspecting the archive: 1795 entries, 0 matching web/ui, 0 matching ui/dist. pyproject excludes `core = ["web/ui/**"]`, `web = ["ui/**"]` and `"*" = ["**/dist/**"]`; release-please.yml runs `python -m build` with no preceding npm build; src/core/web/server.py falls back to the "SPA not built yet" HTML when _SPA_DIST is absent.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a wheel built by the release pipeline, **When** its contents are listed, **Then** `core/web/ui/dist/index.html` and the hashed `assets/*` are present while `ui/src`, `node_modules` and tests are not.
- **Given** that wheel installed into an empty venv, **When** `cos hub start` runs, **Then** `GET /` returns the SPA HTML (not "SPA not built yet") and a referenced `/assets/*` returns 200.
- **Given** the sdist, **When** a wheel is built from it, **Then** the same two checks hold.
- **Given** a wheel missing the SPA, **When** CI runs, **Then** the release is blocked rather than published.

## Work Log
- 2026-08-14 [claude]: Edit pyproject.toml
- 2026-08-14 [claude]: Edit test_wheel_contents.py
- 2026-08-14 [claude]: Edit test_wheel_contents.py
- 2026-08-14 [claude]: Edit release-please.yml
- 2026-08-14 [claude]: Edit release-please.yml
- 2026-08-14 [claude]: Edit test_wheel_contents.py
- 2026-08-14 [claude]: Edit test_wheel_contents.py
- 2026-08-14 [claude]: Edit release-please.yml
- 2026-08-14 [claude]: Edit smoke_wheel_hub.sh
- 2026-08-14 [claude]: Edit smoke_wheel_hub.sh
- 2026-08-14 [claude]: Edit pyproject.toml
- 2026-08-14 [claude]: Edit pyproject.toml
- 2026-08-14 [claude]: Edit scan_flat_imports.py
- 2026-08-14 [claude]: Edit scheduled.py
- 2026-08-14 [claude]: Edit scheduled.py
- 2026-08-14 [claude]: Edit scheduled.py
- 2026-08-14 [claude]: Edit test_wheel_hub_smoke.py
- 2026-08-14 [claude]: Edit test_wheel_hub_smoke.py
- 2026-08-14 [claude]: Edit read_stdin.py
- 2026-08-14 [claude]: Edit test_wheel_contents.py
- 2026-08-14 [claude]: Edit msg5.txt
- 2026-08-14 [claude]: commit 341bb3f5e6 — fix(packaging): make a wheel install actually serve the Hub
- 2026-08-14 [claude]: Fixed in 341bb3f5. The SPA gap was only the first of three: with ui/dist packaged, a fresh-venv install still crashed…
- 2026-08-14 [claude]: Status transitioned to complete via cos task-done.
