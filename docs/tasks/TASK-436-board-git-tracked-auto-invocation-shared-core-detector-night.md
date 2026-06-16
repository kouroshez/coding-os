---
id: TASK-436
title: "board.git_tracked auto-invocation: shared core detector + nightly board-task (idempotent) + CI gate"
swimlane: infra
kind: feature
epic: null
labels: [board_os, doctor, coherence, nightly, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-16
started: 2026-06-16
completed: 2026-06-16
agent_session: ses-803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-436: board.git_tracked auto-invocation: shared core detector + nightly board-task (idempotent) + CI gate

**Outcome (one sentence):** The board.git_tracked drift detection (shipped as a cos doctor check in TASK-432) also runs WITHOUT anyone invoking cos doctor, so no-hook personas are covered: the detection logic is extracted into a shared core module (src/core/board_os/) consumed by both the doctor check and a new nightly cron task that files an idempotent board task on drift (visible on the Hub board to human/chat personas P4/P5/P7), plus a CI gate (P6) that exits non-zero on board↔git drift in the checked-out tree.

## Read First
- src/cli/doctor_board.py
- src/core/scheduled/nightly.py
- .github/workflows/ci.yml
- docs/tasks/TASK-432-board-git-tracked-doctor-check-persona-independent-invocatio.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the doctor check and nightly both need drift detection, **When** the logic is extracted to src/core/board_os/git_coherence.py, **Then** doctor_board._check_git_tracked imports it (no core→cli dependency) and its tests still pass.
**Given** persistent drift on a registered project, **When** the nightly cron runs twice, **Then** it files exactly ONE board task (idempotent via an open auto-git-drift label check), rendered on the Hub board.
**Given** a PR, **When** CI runs, **Then** a job asserts no board↔git drift in the checked-out tree and exits non-zero on drift.

## Work Log
- 2026-06-16 [claude]: Edit git_coherence.py
- 2026-06-16 [claude]: Edit doctor_board.py
- 2026-06-16 [claude]: Edit nightly.py
- 2026-06-16 [claude]: Edit nightly.py
- 2026-06-16 [claude]: Edit ci.yml
- 2026-06-16 [claude]: Edit test_git_coherence.py
- 2026-06-16 [claude]: Edit test_board_coherence.py
- 2026-06-16 [claude]: Edit test_git_coherence.py
- 2026-06-16 [claude]: Edit test_board_coherence.py
- 2026-06-16 [claude]: Edit test_board_coherence.py
- 2026-06-16 [claude]: Edit test_board_coherence.py
- 2026-06-16 [claude]: Edit nightly.py
- 2026-06-16 [claude]: Edit git_coherence.py
- 2026-06-16 [claude]: Edit test_board_coherence.py
- 2026-06-16 [ses-803-0b9f]: Extracted board↔git drift detection to src/core/board_os/git_coherence.py (pure, no core→cli dep); doctor_board._check_g
- 2026-06-16 [claude]: committed f394d4d7 · 6 files
