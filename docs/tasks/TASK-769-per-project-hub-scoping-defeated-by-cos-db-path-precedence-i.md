---
id: TASK-769
title: "Per-project Hub scoping defeated by $COS_DB_PATH precedence in resolve_db_path \u2014 every project shows coding-os"
swimlane: core
kind: bug
epic: null
labels: [hub, scoping, multi-project, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-07-04
started: 2026-07-03
completed: 2026-07-03
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-769: Per-project Hub scoping defeated by $COS_DB_PATH precedence in resolve_db_path — every project shows coding-os

**Outcome (one sentence):** A scoped Hub request resolves to that project's DB, not the ambient COS_DB_PATH. resolve_db_path honors a bound per-request project scope above the env var; CLI/hook behavior unchanged (the ContextVar is set only by ProjectScopeMiddleware).

## Read First
- src/core/thinking_os/database.py
- src/core/web/_project_context.py
- docs/engineering/hub-architecture.md

## Repro Steps
`curl /api/p/streamos/board/list` returns coding-os TASK-626, identical to unscoped `/api/board/list`. Root cause: database.py resolve_db_path checks `$COS_DB_PATH` before the bound `_active_project_root` scope, and the hub inherits COS_DB_PATH from its launch dir (coding-os).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the hub launched from coding-os with COS_DB_PATH exported **When** a client calls `GET /api/p/streamos/board/list` **Then** it returns streamos's tasks, not coding-os's.
- **Given** a CLI/MCP call with COS_DB_PATH set and no bound project scope **When** `resolve_db_path()` runs **Then** it still returns `$COS_DB_PATH` (no regression for non-web callers).
- **Given** the fix **When** `pytest src/core/thinking_os/tests/test_db.py` runs **Then** the new bound-scope precedence test passes and the suite stays green.

## Work Log
- 2026-07-04 [claude]: Deliberation: chose to reorder resolve_db_path so the bound _active_project_root ContextVar is checked BEFORE…
- 2026-07-04 [claude]: Edit database.py
- 2026-07-04 [claude]: Edit test_db.py
- 2026-07-04 [claude]: Verified + committed 16b863f3. New regression test test_resolve_db_path_bound_scope_beats_env passes; test_db.py…
