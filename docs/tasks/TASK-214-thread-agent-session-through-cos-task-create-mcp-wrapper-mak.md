---
id: TASK-214
title: "Thread agent_session through cos_task_create MCP wrapper \u2014 make TASK-212 create-path attribution functional"
swimlane: core
kind: bug
epic: agent-hub
labels: [mcp, attribution, concurrency, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-06
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260605-233300-41f3
depends_on: []
blocked_by: []
references: []
---
# TASK-214: Thread agent_session through cos_task_create MCP wrapper — make TASK-212 create-path attribution functional

**Outcome (one sentence):** The cos_task_create MCP server wrapper (src/core/thinking_os/server.py) declares an `agent_session: str = ""` parameter and threads `agent_session or _detect_agent_session_default()` into `_board_mcp.cos_task_create(...)`, mirroring cos_task_move — so the inject-mcp-caller-session hook's injected `agent_session` is honored for the create path instead of being silently dropped by FastMCP (which discards undeclared kwargs). Completes the create third of TASK-212's attribution claim; the board layer (board_os/mcp_tools.py::cos_task_create) already accepts and stamps agent_session.

## Read First
- src/core/thinking_os/server.py (cos_task_create wrapper ~1651-1685; cos_task_move ~1874-1889 as the pattern)
- src/core/board_os/mcp_tools.py (cos_task_create accepts agent_session ~489-505)
- src/core/hooks/inject-mcp-caller-session.sh (injects agent_session for cos_task_create)

## Repro Steps
1. Read server.py cos_task_create (1651-1664): the wrapper signature has NO agent_session, and the body (1671-1685) never passes one.
2. Contrast cos_task_move (1874-1889): it declares agent_session and threads `agent_session or _detect_agent_session_default()`.
3. The inject-mcp-caller-session hook DOES emit agent_session for cos_task_create, but FastMCP silently drops the undeclared kwarg, so create attribution still falls to the last-writer-wins .active-session pointer.
Expected: an injected (or explicit) agent_session is honored on create.
Actual: silently dropped; create-path attribution unfixed.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a cos_task_create MCP call carrying agent_session (injected by the hook or explicit)
- **When** the server wrapper runs
- **Then** it threads the resolved session into _board_mcp.cos_task_create so the created task's history/owner is stamped with the calling panel (not .active-session); mirrors cos_task_move; `python src/core/thinking_os/server.py --test` passes and `uv run --extra rag pytest src/core/thinking_os/tests/ -q` is green; no MCP signature break (the param is optional, default "").

## Work Log
- 2026-06-06 [claude]: Fixed: cos_task_create server wrapper now declares agent_session and threads (agent_session or _detect_agent_session_def
- 2026-06-06 [claude]: committed 5cdf71ae: src/core/thinking_os/server.py
