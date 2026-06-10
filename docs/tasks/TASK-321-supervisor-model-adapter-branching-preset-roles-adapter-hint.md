---
id: TASK-321
title: "Supervisor model/adapter branching \u2014 preset roles_adapter_hints in registry.yaml consulted at dispatch build"
swimlane: "thinking_os"
kind: feature
epic: null
labels: [delegation, model-routing, audit-2026-06-09, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-10
started: null
completed: null
agent_session: null
depends_on: [TASK-308, TASK-317]
blocked_by: []
references: []
---

# TASK-321: Supervisor model/adapter branching — preset roles_adapter_hints in registry.yaml consulted at dispatch build

**Outcome (one sentence):** Preset chains accept optional per-role adapter/model hints; `_build_dispatch_request` resolves the model via precedence explicit-arg > preset hint > role model_pref > cos_route_model empirical > None — all data-driven config, zero code-level model literals; cos_supervise surfaces the suggestion in its dispatch action.

## Read First
- src/core/thinking_os/presets/registry.yaml (hint schema lands here)
- src/core/thinking_os/tools/cognition.py (_build_dispatch_request — precedence helper)
- src/core/thinking_os/tools/routing.py (cos_route_model fallback tier)
- docs/adapters/claude-sdk.md (spec the precedence table FIRST — Rule 19)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a preset declaring `roles_adapter_hints: {reviewer: {model_pref: {complex: opus}}}` and a COMPLEX gate
- **When** the reviewer formula dispatches
- **Then** DispatchRequest.model resolves from the preset hint and the formula_dispatches row records it
- **Given** no hint anywhere and routing history present
- **When** dispatch builds
- **Then** cos_route_model's recommendation is used and the decision source is traced
- **Given** Rule 11 sweep tests
- **When** they run over the diff
- **Then** no hardcoded model/adapter literals in cognition.py — registry/settings only

## Work Log
