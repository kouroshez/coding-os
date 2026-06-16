---
id: TASK-432
title: "board.git_tracked doctor check + persona-independent invocation (nightly board-task + CI gate) for board\u2194git drift"
swimlane: infra
kind: feature
epic: null
labels: [board_os, doctor, coherence, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-16
started: 2026-06-15
completed: 2026-06-16
agent_session: ses-claude-20260615-232816-54b1
depends_on: []
blocked_by: []
references: []
---
# TASK-432: board.git_tracked doctor check + persona-independent invocation (nightly board-task + CI gate) for board↔git drift

**Outcome (one sentence):** board↔git drift is detectable on demand by every persona via a read-only WARN cos doctor check, board.git_tracked, that flags DB task rows whose docs/tasks/*.md is untracked/modified or missing; the git invocation is work-tree-guarded (porcelain -z + show-toplevel) so it never errors or walks up to a parent repo (auto-invocation for no-hook personas split to TASK-436).

## Read First
- src/cli/doctor_board.py
- src/core/scheduled/nightly.py
- docs/playbooks/doctor-checks.md
- docs/tasks/TASK-398-board-os-sync-integrity-conflict-detection-sync-dead-frontma.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a DB task row whose .md is untracked or modified-uncommitted, **When** cos doctor runs, **Then** board.git_tracked emits SEV_WARN naming the task_id; reverse drift (DB row with missing .md) also WARNs; all-committed yields PASS.
**Given** cwd is not a git work-tree root, **When** the check runs, **Then** it fails open (skip/PASS) and never reports a parent repo (porcelain -z + show-toplevel guard).
**Given** the change, **When** tests/test_doctor_board_git_tracked.py runs, **Then** all 4 cases pass (untracked→WARN, missing-file→WARN, clean→PASS, non-git→skip).
**Note:** the persona-independent AUTO-invocations (nightly board-task for no-hook personas P4/P5/P7 + CI gate for P6) are split to TASK-436 — they need a shared core-side detector extraction, kept out of this overloaded session.

## Work Log
- 2026-06-16 [claude]: Edit doctor_board.py
- 2026-06-16 [claude]: Edit doctor_board.py
- 2026-06-16 [claude]: Edit doctor_board.py
- 2026-06-16 [claude]: Edit doctor_board.py
- 2026-06-16 [claude]: Edit test_doctor_board_git_tracked.py
- 2026-06-16 [claude]: Edit doctor-checks.md
- 2026-06-16 [claude]: Edit TASK-432-board-git-tracked-doctor-check-persona-independent-invocatio.md
- 2026-06-16 [claude]: Edit TASK-432-board-git-tracked-doctor-check-persona-independent-invocatio.md
- 2026-06-16 [claude]: Status transitioned to complete via cos task-done.
