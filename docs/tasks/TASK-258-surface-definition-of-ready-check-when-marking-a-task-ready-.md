---
id: TASK-258
title: "Surface Definition-of-Ready check when marking a task ready (reuse validator)"
swimlane: "board_os"
kind: feature
epic: board-reliability
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-258: Surface Definition-of-Ready check when marking a task ready (reuse validator)

**Outcome (one sentence):** `cos_task_ready` runs the existing Definition-of-Ready validator and surfaces gaps, so a task is never silently labeled `ready` while incomplete — warn by default, `COS_READY_DOR=strict` blocks unless `COS_DOR_OVERRIDE=1` + reason.

## Read First
- src/core/board_os/transition_gates_validator.py — `evaluate_dor(kind, body, config) -> ValidationResult` (~line 205, the PURE checker to REUSE) + `evaluate_override` (~290) + `ValidationResult/ValidationMessage/Verdict` shape.
- src/core/board_os/mcp_tools.py — `cos_task_ready` (~line 1367, the tool to extend) + helpers `_labels_list_from_json`, `_project_root`, `sync_one`, the `ok/fail` envelope.
- src/core/board_os/workflow.py — `validate_transition` wiring (~line 399): copy how it loads `GatesConfig` + the task `body` + `kind` so the new call reuses the same loading (DRY).
- src/core/board_os/transition-gates.yaml — the per-kind DoR section config the validator reads.
- docs/governance/mcp-tool-inventory.md — `cos_task_ready` entry to update FIRST (Rule 19 doc-first).

## Context / Approach
DoR is ALREADY enforced as a hard gate at `icebox→in_progress` (workflow.py via `validate_transition`/`evaluate_dor`). But the `ready` LABEL — what makes a task pullable — is toggled by `cos_task_ready` with NO DoR check, so an author can mark a task `ready` while it's still incomplete (the exact failure the user hit). Fix at the authoring moment by REUSING the existing validator (Rule 22 — no new validation logic):

1. In `cos_task_ready`, when `ready=True` and not a no-op, load `GatesConfig` + the task `body` + `kind` (mirror workflow.py) and call `evaluate_dor`.
2. **Default = warn:** still set the label; return the gap list in `meta.dor` (codes + messages from ValidationResult). The author sees "ready set, but DoR incomplete: Read First missing".
3. **`COS_READY_DOR=strict` = block:** refuse the label with `fail("validation", …)` listing the gaps, UNLESS `COS_DOR_OVERRIDE=1` + `COS_OVERRIDE_REASON` (reuse `evaluate_override`). Mirrors the repo's warn-default/strict-block + override idiom (enforce-graph-context, validate_transition).
4. CLI parity: ensure `cos task-ready` surfaces the same `meta.dor` (it routes through the shared function).
5. Non-breaking by default → existing tests that ready minimal tasks keep passing (they just get a warn). Removing the label (`ready=False`) is never gated.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a task whose body still has the placeholder Read First, **When** `cos_task_ready(ready=True)` runs in default mode, **Then** the label is set AND `meta.dor` lists the DoR gap (non-blocking).
- **Given** the same task with `COS_READY_DOR=strict`, **When** `cos_task_ready(ready=True)` runs, **Then** it returns `fail("validation", …)` and the label is NOT set.
- **Given** strict mode + `COS_DOR_OVERRIDE=1` with a ≥15-char reason, **When** it runs, **Then** the label is set and the override is recorded.
- **Given** a fully DoR-complete task, **When** `cos_task_ready` runs, **Then** no `meta.dor` gaps and behavior is unchanged.

## Work Log
- 2026-06-08 [claude]: cos_task_ready now reuses evaluate_dor: warn-default surfaces gaps in data.dor, COS_READY_DOR=strict blocks unless COS_D
- 2026-06-08 [claude]: Status transitioned to complete via cos task-done.
