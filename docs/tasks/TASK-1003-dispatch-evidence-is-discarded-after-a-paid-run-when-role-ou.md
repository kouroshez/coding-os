---
id: TASK-1003
title: "Dispatch evidence is discarded after a paid run when role output misses its schema"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [cognition, dispatch, schema]
status: icebox
priority: P2
appetite: 1d
created: 2026-08-17
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1003: Dispatch evidence is discarded after a paid run when role output misses its schema

**Outcome (one sentence):** A successful dispatch always leaves an evidence row: either the SDK enforces the role's declared schema at generation time (structured_output on), or a near-miss payload is persisted with a degraded marker instead of being dropped after the tokens were already spent.

## Read First
- src/core/thinking_os/_cognition_artifacts.py
- src/core/thinking_os/tools/_dispatch_persistence.py
- src/adapters/claude/_claude_sdk_options.py
- src/core/thinking_os/agents/analyst.md

## Repro Steps
1. Dispatch `analyst` for real (verified 2026-08-17: `status=ok`, adapter=claude, model=claude-haiku-4-5). 2. The sub-agent returns `dependencies.nodes` as a list of objects (`{'id': 'cos doctor', 'type': ..., 'path': ...}`), but `_cognition_artifacts.DependencyGraph.nodes` is `list[str]` → `AnalystOutput.model_validate` raises `string_type`. 3. `_dispatch_persistence._persist_dispatch_output` sets `validation_failed=True` and **skips the INSERT entirely**, so the run leaves no row — the adapter/model columns stay NULL for this role despite a successful, billed dispatch. 4. Root enabler: only 4 of 14 roles declare `structured_output: true` (`grep -c '^structured_output: true' src/core/thinking_os/agents/*.md`), so for the other 10 the SDK never enforces the schema and the mismatch surfaces only at persistence time. 5. Same run also logged `cos_dispatch_formula_run returned an unshrinkable envelope (40899 chars > 32000 budget)`.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a role that declares an `output_schema`
**When** it is dispatched
**Then** either the SDK enforces that schema during generation, or the returned payload validates against it.

**Given** a dispatch that returned `status=ok` but failed schema validation
**When** persistence runs
**Then** a row is still written with a degraded marker, because the run was already paid for and its route is evidence.

**Given** `analyst` specifically
**When** it is dispatched and the row is inspected
**Then** `adapter` and `model` are non-NULL.

## Work Log
