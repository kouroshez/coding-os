---
id: TASK-660
title: "Harden board\u2194git coherence: opt-in auto-commit of docs/tasks drift + fix silent drift-task filing"
swimlane: infra
kind: feature
epic: null
labels: [board-coherence, git-drift, scheduled, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-30
started: 2026-06-30
completed: 2026-06-30
agent_session: ses-claude-20260628-125542-fc9a
depends_on: []
blocked_by: []
references: []
---
# TASK-660: Harden board↔git coherence: opt-in auto-commit of docs/tasks drift + fix silent drift-task filing

**Outcome (one sentence):** Recurring board↔git drift stops piling up uncommitted — the nightly `board_coherence` cron, when autonomy permits, commits ONLY `docs/tasks/*.md` in one idempotent tasks-only commit (the `_post_commit_body.sh` hook no-ops on a tasks-only commit, so it converges in one pass with zero re-dirty); when autonomy is off it still files exactly ONE `auto-git-drift` board task — and the silent filing bug (`filed:true` but `task_id:null`) is fixed so the nagger actually nags.

## Read First
- src/core/scheduled/nightly.py
- src/core/board_os/git_coherence.py
- src/scripts/_post_commit_body.sh
- docs/governance/task-lifecycle.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** board↔git drift exists (untracked/modified `docs/tasks/*.md` whose DB rows are real) and the project's autonomy setting permits auto-commit
**When** the nightly `board_coherence` task runs
**Then** it stages and commits ONLY `docs/tasks/*.md` in one idempotent, conventional `chore(board):` commit, leaving the tree clean (post-commit hook no-ops → zero re-dirty).

**Given** drift persists and autonomy does NOT permit auto-commit
**When** the nightly `board_coherence` task runs
**Then** it files exactly ONE idempotent `auto-git-drift` board task AND the returned `task_id` is non-null (the `filed` flag reflects whether a task_id was actually minted).

**Then** `uv run --extra rag --with aiohttp --with pytest-asyncio pytest src/core/board_os/tests -q` and the scheduled `test_board_coherence.py` suite are green.

## Notes
- SSOT: `.md` is git-tracked truth; the DB is a gitignored derived index (`sync.py`). Drift = a DB row whose `.md` is uncommitted. Detector: `git_coherence.py` (TASK-436).
- Layer-2 (`committed <sha>` work-log line) is absorbed by E1: a tasks-only commit triggers no post-commit line.

## Work Log
- 2026-06-30 [claude]: Edit task-lifecycle.md
- 2026-06-30 [claude]: Edit nightly.py
- 2026-06-30 [claude]: Edit test_board_coherence.py
- 2026-06-30 [claude]: Edit test_board_coherence.py
- 2026-06-30 [claude]: E2 decision: session-close auto-commit NOT added — session-end.sh excludes docs/tasks by design (batch-reconcile, not…
- 2026-06-30 [claude]: R1 decision: layer-2 committed-sha line kept as-is — tasks-only auto-commit produces no post-commit line (hook no-ops…
