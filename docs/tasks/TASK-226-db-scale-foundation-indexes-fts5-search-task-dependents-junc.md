---
id: TASK-226
title: "DB scale foundation: indexes + FTS5 search + task_dependents junction table (kills LIKE O(n^2))"
swimlane: "board_os"
kind: feature
epic: enterprise-scale
labels: [scale, db, index, migration, ready]
status: complete
priority: P1
appetite: 2d
created: 2026-06-07
started: 2026-06-07
completed: 2026-06-07
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-226: DB scale foundation: indexes + FTS5 search + task_dependents junction table (kills LIKE O(n^2))

**Outcome (one sentence):** The DB carries the indexes every keyset query needs at 100K+ rows (append-only migrations, Rule 9): (status, completed_at) and (swimlane, status, priority) on tasks; (task_id, transitioned_at) on task_status_history; FTS5 on tasks(title, goal/body) so cos_task_search stops full-scanning; a task_dependencies junction table replacing the depends_on LIKE scan (O(n^2) -> indexed). This is the foundation pulled first by board pagination (TASK-223) + bounded queries (TASK-227). Verified by EXPLAIN QUERY PLAN showing index use + migration tests green. See audit-enterprise-scale-2026-06-07.md.

## Read First
- docs/tasks/audits/audit-enterprise-scale-2026-06-07.md
- src/core/thinking_os/database.py
- src/core/board_os/mcp_tools.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** 100K tasks + their status-history and dependency rows.
- **When** the board/search/dependency queries run after the new append-only migrations.
- **Then** indexes exist on tasks(status, completed_at) + (swimlane, status, priority), task_status_history(task_id, transitioned_at); an FTS5 table backs cos_task_search; a task_dependencies junction replaces the depends_on LIKE scan; EXPLAIN QUERY PLAN shows index/FTS use (no full scan) and migration tests are green (no edit to past migrations).

## Work Log
- 2026-06-07 [claude]: committed 44285ff6: src/core/board_os/sync.py, src/core/thinking_os/database.py, src/core/thinking_os/tests/test_db.py,
- 2026-06-07 [claude]: committed 44285ff6: v35 (keyset indexes + regular FTS5 + task_dependencies junction via triggers off dependencies column
- 2026-06-07 [claude]: Status transitioned to complete via cos task-done.
