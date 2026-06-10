---
id: TASK-308
title: "Wire role model_pref into _build_dispatch_request \u2014 dispatch always sends model=None (dead spec)"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [ready, model-routing, spec-drift, audit-2026-06-09]
status: icebox
priority: P1
appetite: 1d
created: 2026-06-10
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-308: Wire role model_pref into _build_dispatch_request — dispatch always sends model=None (dead spec)

**Outcome (one sentence):** A role whose frontmatter declares `model_pref` (e.g. reviewer: complicated→sonnet, complex→opus) actually dispatches with `DispatchRequest.model` derived from model_pref × current gate complexity, and `cos_dispatch_formula_run` accepts an explicit `model` override.

## Read First
- src/core/thinking_os/tools/cognition.py (`_build_dispatch_request`, ~L1154 — model never set)
- src/core/thinking_os/dispatcher.py (DispatchRequest.model contract)
- src/core/thinking_os/agents/README.md (model_pref spec, L36-38)
- docs/engineering/dispatcher-contract.md

## Repro Steps
1. Pick any role with `model_pref` in frontmatter (e.g. agents/reviewer.md declares complex→opus).
2. Run `cos_dispatch_formula_run` for that role with a COMPLEX gate recorded.
Expected: DispatchRequest.model = the model_pref entry for the gate complexity.
Actual: model=None always — model_pref is parsed and returned by cos_dispatch_formula but never forwarded (Rule 19 spec-vs-code drift).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a role with `model_pref: {complex: opus}` and a recorded COMPLEX gate
- **When** `cos_dispatch_formula_run` dispatches that role
- **Then** the dispatcher receives `model` resolved from model_pref and the formula_dispatches row records the model used
- **Given** an explicit `model` argument to `cos_dispatch_formula_run`
- **When** dispatch runs
- **Then** the explicit argument overrides model_pref; covered by a thinking_os pytest

## Work Log
