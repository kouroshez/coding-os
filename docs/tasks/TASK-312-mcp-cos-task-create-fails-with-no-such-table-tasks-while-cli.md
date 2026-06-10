---
id: TASK-312
title: "MCP cos_task_create fails with 'no such table: tasks' while CLI works \u2014 DB path or migration drift in MCP server"
swimlane: "board_os"
kind: bug
epic: null
labels: [ready, mcp, db-path, audit-2026-06-09]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-10
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-312: MCP cos_task_create fails with 'no such table: tasks' while CLI works — DB path or migration drift in MCP server

**Outcome (one sentence):** `cos_task_create` invoked through the MCP server succeeds against the same board DB the CLI uses, with a regression test asserting CLI and MCP resolve identical DB paths/schema.

## Read First
- src/core/board_os/mcp_tools.py (cos_task_create MCP path)
- src/core/thinking_os/database.py (DB resolution + migrations)
- src/core/board_os/sync.py (file↔DB sync — CLI path that works)

## Repro Steps
1. In this repo (2026-06-09 session), call MCP `cos_task_create` with valid args (title/swimlane/kind, ready=True).
2. Observe envelope: `{"ok": false, "error": {"category": "internal", "message": "OperationalError: no such table: tasks"}}`.
3. Same create via `cos task-create` CLI succeeds (created TASK-308..312). Note: `cos_task_edit` and `cos_task_show` via MCP work — failure is isolated to the create path's DB handle.
Expected: MCP create succeeds like CLI.
Actual: MCP create hits a DB missing the `tasks` table (wrong $COS_DB_PATH resolution or un-migrated handle in server runtime).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the MCP server running in this repo
- **When** `cos_task_create` is called with valid args
- **Then** it returns ok with a task_id and `cos task-show` finds the task
- **Given** the root cause (path vs migration)
- **When** fixed
- **Then** a board_os test asserts MCP and CLI create paths resolve the same DB and schema (guards regression)

## Work Log
