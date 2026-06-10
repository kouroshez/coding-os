---
id: TASK-312
title: "MCP cos_task_create fails with 'no such table: tasks' while CLI works \u2014 DB path or migration drift in MCP server"
swimlane: "board_os"
kind: bug
epic: null
labels: [ready, mcp, db-path, audit-2026-06-09]
status: testing
priority: P2
appetite: 1d
created: 2026-06-10
started: 2026-06-09
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-312: MCP cos_task_create fails with 'no such table: tasks' while CLI works — DB path or migration drift in MCP server

**Outcome (one sentence):** The transient `no such table: tasks` on the MCP create path is made impossible-or-diagnosable: `@safe_tool` logs full traceback + DB identity server-side (today it swallows them — confirmed: zero trace in any log), and the shared single `sqlite3.Connection` across the FastMCP threadpool is hardened (per-call connections under WAL, or a write lock).

## Read First
- src/core/thinking_os/tools/_shared.py (@safe_tool — wraps exception into envelope, logs nothing)
- src/core/thinking_os/server.py:51 (`_db_conn = init_db()` — one conn shared by ALL tools; FastMCP runs sync tools in a threadpool)
- src/core/thinking_os/database.py:2264 (`check_same_thread=False` on the shared conn)
- src/core/board_os/mcp_tools.py (cos_task_create / _next_task_id)

## Repro Steps (investigation 2026-06-09, ses-...-214517)
1. 3 parallel MCP cos_task_create calls; the one passing validation failed `OperationalError: no such table: tasks`. CLI create + MCP edit/show/board on the SAME conn worked before/after; a later identical MCP create succeeded (TASK-315 probe) → transient.
2. Ruled out WITH evidence: env/DB path (all 5 server PIDs hold the correct 209MB coding-os.db open — lsof + ps eww), missing table (sqlite_master has `tasks`), tasks_fts trigger (probe shows trigger failure says `main.tasks_fts`, direct says `tasks` — ours was direct), legacy rename (guarded by target.exists()), board migration.py (file-level only), helper conns (_resolve_attribution/_detect_agent_session_default are file/env readers).
3. Remaining architectural suspect: one `check_same_thread=False` connection shared across concurrent tool threads (parallel calls DID overlap at failure time). Regardless of exact trigger, this sharing is unsound and unobservable.
Expected: deterministic create; on any internal error, a server-side traceback exists.
Actual: transient failure, zero forensic trail (fail envelope is the only record).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** any `@safe_tool` tool raising an exception
- **When** the fail envelope is returned
- **Then** the server log carries the full traceback + tool name + thread id + `PRAGMA database_list` snapshot for sqlite errors
- **Given** N concurrent MCP board writes (threadpool)
- **When** they execute
- **Then** no shared-conn cross-thread write interleaving is possible (per-call conn or lock), proven by a multi-thread board_os test (existing concurrency test covers two CONNECTIONS, not two THREADS on one conn — the uncovered window)

## Work Log
- 2026-06-09 investigation: facts + ruled-out matrix above; probe TASK-315 created+archived as repro evidence.
- 2026-06-10 [claude]: Forensics half shipped (score 9/10): traceback found in .coding-os/.mcp.log (dotfile — *.log globs miss it); safe_tool n
