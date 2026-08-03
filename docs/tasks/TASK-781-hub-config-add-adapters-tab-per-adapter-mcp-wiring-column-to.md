---
id: TASK-781
title: "Hub Config: add Adapters tab + per-adapter MCP wiring column + toggle loading/operation-log"
swimlane: core
kind: feature
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-07-04
started: 2026-07-04
completed: 2026-07-04
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-781: Hub Config: add Adapters tab + per-adapter MCP wiring column + toggle loading/operation-log

**Outcome (one sentence):** The Hub Config surface gains an Adapters tab consuming the existing GET /api/config/adapters — each adapter's runtime (in_process/roadmap) + availability + declared chat models (default marked) + its MCP wiring target (claude → .mcp.json, codex → .codex/config.toml) — closing the "endpoint exists but no UI" gap; toggle loading-states + the regenerated-cascade operation log are already implemented for skills + modules (stacks are read-only by design).

## Read First
- src/core/web/ui/src/pages/ConfigPage.tsx
- src/core/web/routes/config.py (config_adapters, ~L184)
- docs/engineering/hub-architecture.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Hub Config surface **When** the user opens the new Adapters tab **Then** it lists each adapter (claude, codex) with a runtime pill (in_process/roadmap), availability, chat models with the default marked, and the MCP config path(s) it wires — reading GET /api/config/adapters (the endpoint's fields, verified against the producer).
- **Given** the config_adapters producer **When** the UI reads mcp wiring **Then** the endpoint exposes each adapter's mcp_launch config paths (additive field), so the UI never guesses the wiring target.
- **Given** the ui build **When** `make ui-build` runs **Then** it type-checks + builds green.

## Work Log
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit test_config_routes.py
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.test.tsx
- 2026-07-04 [claude]: Edit ConfigPage.test.tsx
- 2026-07-04 [claude]: commit 14997c4179 — feat(hub): add Config Adapters tab with runtime, models, and MCP wiring
- 2026-07-04 [claude]: Added the Hub Config Adapters tab (ConfigPage.tsx) consuming GET /api/config/adapters: per-adapter runtime pill…
