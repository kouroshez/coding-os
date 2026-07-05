---
id: TASK-787
title: "Converge $HOME DB guard and Work Log edit-race from third max-effort review: restore resolve_db_path raise, producer fresh-worklog swap"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-07-04
started: 2026-07-04
completed: null
agent_session: ses-claude-20260703-210450-473d
depends_on: []
blocked_by: []
references: []
---
# TASK-787: Converge $HOME DB guard and Work Log edit-race from third max-effort review: restore resolve_db_path raise, producer fresh-worklog swap

**Outcome (one sentence):** resolve_db_path raises at bare $HOME again (the complete guard covering direct-connect graph/cognition paths that bypass init_db); cos_task_edit swaps the fresh on-disk Work Log in place so a concurrent append is never lost and an H1-only body diff records no phantom edit; the Work Log heading regex is shared with cos_work_log_append; docs + tests updated to match.

## Read First
- src/core/thinking_os/database.py
- src/core/board_os/mcp_tools.py
- src/core/graph_os/backends/sqlite_backend.py
- docs/engineering/hub-architecture.md

## Repro Steps
Third max-effort /code-review of 955678c4+ca567ef1 found: database.py init_db guard is bypassed by graph SqliteBackend/cognition direct sqlite3.connect (phantom DB reopened); removing producer Work Log preservation reintroduced a concurrent-append data-loss race; editBody strips H1 so every drawer save records a phantom body edit.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** resolve_db_path at bare $HOME with no scope/env/arg **When** the graph SqliteBackend or cognition route resolves a path **Then** it raises (no phantom DB minted), because all DB-open paths funnel through resolve_db_path. **Given** a task whose Work Log gained a line after the drawer snapshotted the body **When** the stale body is saved **Then** the fresh line survives and no phantom body edit is recorded. **Given** a drawer save that changes only the title **When** cos_task_edit runs **Then** changed does not include body.

## Work Log
- 2026-07-04 [claude]: Edit database.py
- 2026-07-04 [claude]: Edit database.py
- 2026-07-04 [claude]: Edit test_db.py
- 2026-07-04 [claude]: Edit test_db.py
- 2026-07-04 [claude]: Edit mcp_tools.py
- 2026-07-04 [claude]: Edit mcp_tools.py
- 2026-07-04 [claude]: Edit mcp_tools.py
- 2026-07-04 [claude]: Edit task-lifecycle.md
- 2026-07-04 [claude]: Edit hub-architecture.md
- 2026-07-04 [claude]: Edit test_mcp_tools.py
- 2026-07-04 [claude]: Edit test_mcp_tools.py
- 2026-07-04 [claude]: Third max-effort review converged the $HOME guard + Work Log edit (prior two rounds oscillated). RESTORED…
