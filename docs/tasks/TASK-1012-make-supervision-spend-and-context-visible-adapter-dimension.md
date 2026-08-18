---
id: TASK-1012
title: "Make supervision spend and context visible: adapter dimension, doctor check, dispatch context"
swimlane: "thinking_os"
kind: feature
epic: null
labels: [supervision, observability, hub, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-18
started: 2026-08-18
completed: 2026-08-18
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-1012: Make supervision spend and context visible: adapter dimension, doctor check, dispatch context

**Outcome (one sentence):** An operator can answer "how much did Claude cost vs Codex" from the Hub and `cos doctor` reports whether supervision is actually routing, and a dispatched sub-agent receives the task it is working on instead of only its role prompt.

## Read First
- src/core/web/routes/cognition_dispatch_views.py
- src/core/web/ui/src/features/cognition/CostPanel.tsx
- src/cli/_doctor_cognition.py
- src/core/thinking_os/dispatcher.py
- src/adapters/codex/sdk_dispatcher.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** dispatch rows carrying `adapter` and `model`
**When** /api/cognition/cost is queried
**Then** the payload carries a per-adapter rollup and the rows name adapter and model, so Claude vs Codex spend is separable.

**Given** the Hub Cognition tab
**When** CostPanel renders
**Then** it shows the per-adapter split, not only formula × day.

**Given** `model_routing.enabled` is true but no dispatch has ever recorded an adapter
**When** `cos doctor` runs
**Then** a supervision check WARNs that routing is configured but never exercised, naming the pinned roles.

**Given** a role dispatched to any adapter
**When** the sub-agent receives its prompt
**Then** the prompt carries the active task id, outcome and recent work log, so the sub-agent is not blind to the work it is judging.

**Given** the changes
**When** the Verification Matrix rows for thinking_os, web routes, cli and ui run
**Then** they pass, and a real dispatch is executed and its recorded adapter/model/cost inspected.

## Work Log
- 2026-08-18 [claude]: Three gaps closed plus one blocker found by dogfooding. (1) /api/cognition/cost now groups by adapter+model with a…
- 2026-08-18 [claude]: Blocker found by running a real dispatch, not by reading: cos_dispatch_formula_run(reviewer) failed with "model…
- 2026-08-18 [claude]: commit 3e6b029383 — fix(supervision): resolve tier aliases before validation so dispatch can run
- 2026-08-18 [claude]: Status transitioned to complete via cos task-done.
- 2026-08-18 [claude]: Ran a REAL supervised dispatch rather than handing the step to the operator, and it exposed two more defects the unit…
