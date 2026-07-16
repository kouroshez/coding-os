---
id: TASK-821
title: "Nightly board maintenance commits its own docs/tasks rewrites (stop leaving the tree dirty every night)"
swimlane: core
kind: bug
epic: null
labels: [scheduled, git-hygiene, governance, ready]
status: "in_progress"
priority: P1
appetite: 1d
created: 2026-07-16
started: 2026-07-16
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---

# TASK-821: Nightly board maintenance commits its own docs/tasks rewrites (stop leaving the tree dirty every night)

**Outcome (one sentence):** The nightly reclaim/auto-archive leg commits exactly the docs/tasks/*.md files it rewrote (explicit paths, conventional-commit message), so unattended maintenance no longer leaves 15+ modified task files stranded in the working tree.

## Read First
- docs/engineering/scheduled-jobs.md
- src/core/scheduled/nightly.py
- src/core/board_os/git_coherence.py
- src/core/rules/git-workflow.md

## Repro Steps
Nightly 03:02 sweep archived 15 idle-complete tasks; each transition rewrote the task file frontmatter; `git status` shows all 15 as modified, uncommitted, mixed into every later session's dirty tree.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the nightly reclaim leg archives/reclaims N tasks **When** the leg finishes **Then** the touched task files are committed with `chore(board): ...` (explicit paths only, never -a) and `git status -- docs/tasks` is clean for those files.
**Given** a task file that was already dirty from a foreign session and NOT touched by the sweep **When** the leg commits **Then** that file is untouched.
**Given** dry_run=True **When** the leg runs **Then** no commit happens.

## Work Log
- 2026-07-16 [claude]: Edit task-lifecycle.md
- 2026-07-16 [claude]: Edit nightly.py
- 2026-07-16 [claude]: Edit nightly.py
- 2026-07-16 [claude]: Edit nightly.py
- 2026-07-16 [claude]: Edit nightly.py
- 2026-07-16 [claude]: Edit test_board_coherence.py
- 2026-07-16 [claude]: Edit test_board_coherence.py
- 2026-07-16 [claude]: Edit test_board_coherence.py
- 2026-07-16 [claude]: commit de8fb34bde — fix(core): missing DB rows no longer block the nightly board-drift auto-commit
- 2026-07-16 [claude]: Edit nightly.py
- 2026-07-16 [claude]: commit f0f65a3e32 — fix(core): raise board-drift commit timeout to 600s for large staged sets
