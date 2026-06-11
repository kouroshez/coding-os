---
id: TASK-398
title: "board_os sync integrity \u2014 conflict detection + sync dead frontmatter fields + drop v6 dead columns"
swimlane: "board_os"
kind: bug
epic: null
labels: [task-system-review, ready]
status: complete
priority: P1
appetite: 2d
created: 2026-06-11
started: 2026-06-11
completed: 2026-06-11
agent_session: ses-claude-20260611-120804-a06f
depends_on: []
blocked_by: []
references: []
---
# TASK-398: board_os sync integrity — conflict detection + sync dead frontmatter fields + drop v6 dead columns

**Outcome (one sentence):** File↔DB drift becomes impossible silently: sync_one detects manual frontmatter edits vs transition writes (frontmatter-hash, not mtime-only), frontmatter created/blocked_by/references/external_ref/outcome sync to the DB (or are removed from the parser as dead), the redundant v6 domain column and never-written columns (goal_text, scope_in/out, requirements, source_of_truth, open_questions, rabbit_holes, verification, read_first) are dropped via an append-only migration, and a regression test reproduces the git-checkout-revert silent-divergence case.

## Read First
- src/core/board_os/sync.py
- src/core/board_os/parser.py
- src/core/board_os/workflow.py
- src/core/thinking_os/database.py

## Repro Steps
1. `cos task-move TASK-X --to complete` (DB + MD now say complete).
2. `git checkout -- docs/tasks/TASK-X-*.md` reverting the MD to in_progress (older mtime than the DB row).
3. Run sync_all.
Expected: conflict surfaced (DB is the newer writer) or file re-synced with a warning.
Actual: mtime-unchanged short-circuit skips the file — DB says complete, MD says in_progress, silently divergent. Also: frontmatter blocked_by/references/external_ref/outcome/created are parsed (parser.py:59-67) but never written by sync.py, and 9 v6 columns are never read or written.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a task MD reverted by git after a DB transition, **When** sync_all runs, **Then** the divergence is detected (frontmatter-hash, not mtime) and surfaced — never silently skipped.
- **Given** frontmatter with blocked_by/references/external_ref, **When** sync_one runs, **Then** those fields land in the DB (or the parser no longer claims to parse them).
- **Given** migration vN+1, **When** tests run, **Then** the dead v6 columns (domain, goal_text, scope_in/out, requirements, source_of_truth, open_questions, rabbit_holes, verification, read_first) are gone and test_db stays green.

## Work Log
- 2026-06-11 [claude]: Edit sync.py
- 2026-06-11 [claude]: Edit database.py
- 2026-06-11 [claude]: Edit database.py
- 2026-06-11 [claude]: Edit database.py
- 2026-06-11 [claude]: Edit database.py
- 2026-06-11 [claude]: Edit sync.py
- 2026-06-11 [claude]: Edit task_sync.py
- 2026-06-11 [claude]: Edit test_task_sync.py
- 2026-06-11 [claude]: Edit test_task_tools.py
- 2026-06-11 [claude]: Edit test_db.py
- 2026-06-11 [claude]: Status transitioned to complete via cos task-done.
