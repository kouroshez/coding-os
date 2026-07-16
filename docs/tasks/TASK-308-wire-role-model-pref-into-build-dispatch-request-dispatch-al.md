---
id: TASK-308
title: "Wire role model_pref into _build_dispatch_request \u2014 dispatch always sends model=None (dead spec)"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [ready, model-routing, spec-drift, audit-2026-06-09]
status: archive
priority: P1
appetite: 1d
created: 2026-06-10
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260527-151803-0b9f
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
- 2026-06-10 [claude]: Shipped (score 9.5/10): _build_dispatch_request resolves model = explicit arg > role model_pref[complexity] > SDK defaul
- 2026-06-10 [claude]: committed cfd4673b: docs/adapters/claude-sdk.md, src/core/thinking_os/tests/test_dispatcher.py, src/core/thinking_os/too
- 2026-06-10 [claude]: Status transitioned to complete via cos task-done.
