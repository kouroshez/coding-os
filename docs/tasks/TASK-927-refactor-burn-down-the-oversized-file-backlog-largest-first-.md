---
id: TASK-927
title: "refactor: burn down the oversized-file backlog, largest first, per the Raptor lens"
swimlane: core
kind: refactor
epic: null
labels: [tech-debt, file-size, ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-08-10
started: 2026-08-10
completed: null
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-927: refactor: burn down the oversized-file backlog, largest first, per the Raptor lens

**Outcome (one sentence):** The count of files over the 500-line backstop falls materially from 114 by splitting each remaining god-file along a real cohesion seam — one commit per file, each verified by its Verification-Matrix command — with the public surface of every split module unchanged.

## Read First
- docs/architecture/raptor-consolidation.md
- src/core/rules/anti-overengineering.md
- docs/engineering/ci-gates.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a file is split **When** its matrix suite runs **Then** it passes with no assertion weakened.
**Given** a split lands **When** `python src/core/scripts/check_file_size.py --json` runs **Then** the error_count is lower than before that split.
**Given** a file has no honest cohesion seam **When** it is left whole **Then** a recorded exception in ci-gates.md states why, rather than an arbitrary cut.

## Work Log
- 2026-08-10 [claude]: commit da130a23be — refactor(core): split learning.py and graph.py along their real cohesion seams
