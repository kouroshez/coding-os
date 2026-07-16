---
id: TASK-227
title: "board_os + CLI bounded queries & git batching (daily/retro/pick/reclaim/reconcile/doctor/history)"
swimlane: "board_os"
kind: feature
epic: enterprise-scale
labels: [scale, board, cli, git, ready]
status: archive
priority: P1
appetite: 3d
created: 2026-06-07
started: 2026-06-07
completed: 2026-06-07
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-227: board_os + CLI bounded queries & git batching (daily/retro/pick/reclaim/reconcile/doctor/history)

**Outcome (one sentence):** No board/CLI path loads or git-scans unboundedly at 100K tasks/1M commits: cos_task_daily/retro/pick return counts + top-N (LIMIT), not full card lists; cos_task_reclaim/reconcile batch task-ids into ONE git log --all --grep (not per-task subprocess) and cap concurrency (ProcessPoolExecutor); cos_task_history + _commits_referencing bound git with --max-count; cos doctor replaces full-tree rglob with find -prune. Verified by a 100K-task/100K-commit fixture staying bounded in time + memory.

## Read First
- src/core/board_os/mcp_tools.py
- src/cli/doctor.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fixture with 100K tasks and ~1M commits.
- **When** daily/retro/pick, reclaim/reconcile, history and doctor run.
- **Then** daily/retro/pick return counts + top-N (LIMIT, no full fetchall); reclaim/reconcile issue ONE batched git log --all --grep with capped concurrency (no per-task subprocess); history + _commits_referencing pass --max-count; doctor uses find -prune (no full rglob); all verified bounded in wall-time + memory on the fixture.

## Work Log
- 2026-06-07 [claude]: committed a9f7eef1: src/cli/doctor.py, src/core/board_os/mcp_tools.py, src/core/board_os/tests/test_mcp_tools.py
- 2026-06-07 [claude]: committed a9f7eef1: daily/pick/retro/reclaim/reconcile/archive LIMIT scans (daily 36KB->11KB envelope); _commits_referen
- 2026-06-07 [claude]: Status transitioned to complete via cos task-done.
