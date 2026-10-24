---
id: TASK-1060
title: "fix(board): auto-archive rewrites task files, so the nightly job commits status churn"
swimlane: "board_os"
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-10-24
started: 2026-10-24
completed: 2026-10-24
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1060: fix(board): auto-archive rewrites task files, so the nightly job commits status churn

**Outcome (one sentence):** The complete/icebox→archive sweep changes only the board DB, so 6 of the last 8 nightly `chore(board)` commits (complete→archive + agent_session rewrites) stop happening, and a later file sync never un-archives the card.

## Read First
- docs/engineering/scheduled-jobs.md
- docs/governance/task-lifecycle.md

## Repro Steps
1. `git log --format=%s | grep 'drifted task file'` → 8 commits in 30 days, all at 03:00.
2. `git show 3b8bc75e` → every hunk is `status: complete → archive` plus an `agent_session` rewrite.
3. Source: `_archive_stale_sweep` → `transition(..., file_path=...)` writes the frontmatter; nightly `board_coherence` then commits the modified files.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a complete task older than complete_auto_archive_days **When** _archive_stale_sweep runs **Then** the DB row is archive and the task file is byte-identical
- **Given** an archived row whose file still says complete **When** sync_one re-reads the file **Then** the row stays archive
- **Given** a manual `cos task-move --to archive` **When** it runs **Then** the file is still written (only the sweep is DB-only)

## Work Log
- 2026-10-24 [claude]: Plan: archive-by-age becomes DB-only (transition persist_file=False from the sweep) and sync_one keeps a DB archive…
- 2026-10-24 [claude]: Status transitioned to complete via cos task-done.
