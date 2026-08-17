---
id: TASK-1005
title: "Gate task creation on an explicit pull-state so no card is born invisible"
swimlane: "board_os"
kind: feature
epic: null
labels: [governance, docs-update, board, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-17
started: 2026-08-17
completed: 2026-08-17
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-1005: Gate task creation on an explicit pull-state so no card is born invisible

**Outcome (one sentence):** Creating a card forces an explicit pull-state decision: `cos_task_create` (and `cos task-create`) BLOCK when the result would be an un-ready icebox card, naming the three explicit exits (ready / parked / keep), so DC-2 becomes prevention instead of a Stop-time report.

## Read First
- docs/governance/task-lifecycle.md
- src/core/hooks/warn-abandoned-task.sh
- src/core/hooks/inject-mcp-caller-session.sh
- src/core/hooks/registry.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a `cos_task_create` call with neither `ready=True` nor a `parked`/`keep` label
**When** the PreToolUse gate runs
**Then** it exits 2 with a message naming all three explicit exits, and no card is created.

**Given** a create call that declares any one of `ready=True`, `parked`, or `keep`
**When** the gate runs
**Then** it exits 0 and the card is created unchanged.

**Given** a create that targets a status other than `icebox`
**When** the gate runs
**Then** it exits 0 — the invisibility failure is specific to un-ready icebox.

**Given** `cos task-create` invoked through Bash without `--ready`
**When** the gate runs
**Then** it blocks on the same rule, so the CLI surface is not a bypass.

**Given** the gate is registered
**When** adapter templates are regenerated
**Then** Codex correctly skips the unsupported matcher pair rather than failing to install.

## Work Log
- 2026-08-17 [claude]: Edit task-lifecycle.md
- 2026-08-17 [claude]: Edit task_readiness_check.py
- 2026-08-17 [claude]: Edit enforce-task-readiness.sh
- 2026-08-17 [claude]: Edit enforce-task-readiness.sh
- 2026-08-17 [claude]: Edit registry.yaml
- 2026-08-17 [claude]: Edit subsystems.yaml
- 2026-08-17 [claude]: Edit adapter.yaml
- 2026-08-17 [claude]: Edit codex-pretool-dispatch.sh
- 2026-08-17 [claude]: Edit test_hooks_task_readiness.py
- 2026-08-17 [claude]: enforce-task-readiness.sh added as a PreToolUse gate on both surfaces (cos_task_create + Bash `cos task-create`),…
- 2026-08-17 [claude]: Edit icebox-parking-structural-failure.md
- 2026-08-17 [claude]: Edit task_readiness_check.py
- 2026-08-17 [claude]: Edit task_readiness_check.py
- 2026-08-17 [claude]: Edit test_hooks_task_readiness.py
- 2026-08-17 [claude]: commit d3422c743d — feat(board): block creating a card with no declared pull-state
- 2026-08-17 [claude]: Dogfood caught a false positive within minutes: the gate blocked its own commit because the Bash matcher…
- 2026-08-17 [claude]: Status transitioned to complete via cos task-done.
