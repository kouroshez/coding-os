---
id: TASK-317
title: "Model-routing settings SSOT \u2014 enabled toggle + orchestrator model + data-driven model registry, zero hardcoded ids"
swimlane: core
kind: feature
epic: null
labels: [model-routing, settings, audit-2026-06-09, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-10
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260527-151803-0b9f
depends_on: [TASK-308]
blocked_by: []
references: []
---
# TASK-317: Model-routing settings SSOT — enabled toggle + orchestrator model + data-driven model registry, zero hardcoded ids

**Outcome (one sentence):** A single data-driven settings section (`model_routing: {enabled: false, orchestrator_model, registry}`) governs the whole auto-routing feature — OFF by default keeps it fully out of play everywhere (hub, CLI, hooks); editable from hub Settings; models discovered from adapter yaml/registry, no hardcoded id anywhere (Rule 11).

## Read First
- docs/engineering/hub-architecture.md (settings propagation contract)
- src/core/web/routes/config.py (settings read/write routes)
- .coding-os/hub-settings.json (current settings shape)
- src/adapters/claude/adapter.yaml (where per-adapter model lists can live)
- src/core/thinking_os/tools/routing.py (cos_route_model consumer)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh project with default settings
- **When** any consumer (hub picker, hooks, dispatcher) reads model_routing
- **Then** enabled=false and the feature is completely inert (no UI option, no injected context, no dispatch change)
- **Given** the hub Settings page
- **When** the user enables model_routing and picks an orchestrator model from the registry-driven list
- **Then** the change persists via the existing config route and is readable by kernel consumers (CLI + MCP) without restart
- **Given** Rule 11 tests
- **When** they sweep src for model-id literals in routing/settings code
- **Then** zero hardcoded model/adapter ids — registry only

## Work Log
- 2026-06-10 [claude]: Shipped (score 9/10): model_routing section in hub settings (enabled=false default, orchestrator_model) via routes/setti
- 2026-06-10 [claude]: committed 10e757b6: docs/engineering/hub-architecture.md, src/core/web/routes/settings.py, src/core/web/ui/src/pages/Set
- 2026-06-10 [claude]: Status transitioned to complete via cos task-done.
