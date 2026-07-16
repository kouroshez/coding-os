---
id: TASK-825
title: "Repair 12 docs/tasks parse errors \u2014 2 files with duplicate frontmatter blocks desync their DB rows"
swimlane: core
kind: bug
epic: null
labels: [board, data-repair, ready]
status: in_progress
priority: P3
appetite: 1d
created: 2026-07-16
started: 2026-07-16
completed: null
agent_session: ses-claude-20260716-145309-8189
depends_on: []
blocked_by: []
references: []
---
# TASK-825: Repair 12 docs/tasks parse errors — 2 files with duplicate frontmatter blocks desync their DB rows

**Outcome (one sentence):** sync_all reports 0 parse_errors: TASK-647 and TASK-786 each carry ONE merged frontmatter block (currently two conflicting blocks make sync reject them, so their board rows are frozen stale), and the other 10 parse errors are diagnosed and repaired.

## Read First
- src/core/board_os/sync.py
- src/core/board_os/parser.py
- docs/governance/task-lifecycle.md

## Repro Steps
Run board_os.sync.sync_all on this repo: stats show parse_errors: 12; stderr names TASK-647 (complete vs in_progress) and TASK-786 (complete vs icebox) as duplicate-frontmatter rejects.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the repaired task files **When** sync_all runs **Then** parse_errors == 0 and the two task rows reflect the file's single frontmatter status.

## Work Log
- 2026-07-16 [claude]: Edit repair_dup_frontmatter.py
