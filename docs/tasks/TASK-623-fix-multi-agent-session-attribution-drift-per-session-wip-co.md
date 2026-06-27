---
id: TASK-623
title: "Fix multi-agent session-attribution drift + per-session WIP collision (MCP panel-first parity)"
swimlane: "board_os"
kind: bug
epic: null
labels: [ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-06-27
started: 2026-06-27
completed: null
agent_session: ses-claude-20260627-161919-30e5
depends_on: []
blocked_by: []
references: []
---
# TASK-623: Fix multi-agent session-attribution drift + per-session WIP collision (MCP panel-first parity)

**Outcome (one sentence):** The MCP board-write path (_agent_runtime._read_active_session_pointer) reads the panel-scoped $COS_PANEL_DIR/session-id pointer FIRST, in parity with the CLI path (board_commands._agent_session_id), so two concurrent panels of the same agent resolve to distinct agent_session ids instead of collapsing to one shared agent-level .active-session — eliminating both the session-attribution drift (M2) and the false per-session WIP cap block (M1).

## Read First
- src/core/board_os/_agent_runtime.py
- src/cli/board_commands.py
- src/core/board_os/workflow.py

## Repro Steps
Dogfooded 2026-06-27: `cos task-start TASK-622` from session 30e5 bound agent_session to sibling session a565; the second live session needed COS_WIP_OVERRIDE=1 to start any task because the per-session in_progress cap counted both panels under one collapsed session id.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** two concurrent panels of the same agent write to the board through the long-lived MCP server, each panel having a distinct `$COS_PANEL_DIR/session-id` pointer
- **When** each panel calls a board mutator (cos_task_move / cos_task_create / cos_work_log_append) whose session is resolved by `_read_active_session_pointer`
- **Then** each write is attributed to its own panel session (not the last-writer-wins agent-level `.active-session`); AND when `$COS_PANEL_DIR` is unset/empty the resolution is byte-identical to today (additive, no regression); AND a unit test in `test_agent_runtime.py` asserts panel-first precedence over the agent-level pointer.

## Work Log
- 2026-06-27 [claude]: Edit _agent_runtime.py
- 2026-06-27 [claude]: Edit test_agent_runtime.py
- 2026-06-27 [claude]: Edit test_agent_runtime.py
- 2026-06-27 [claude]: Edit conftest.py
- 2026-06-27 [claude]: Root-caused M1+M2 to ONE defect: MCP _read_active_session_pointer read agent-shared $COS_AGENT_DIR/.active-session…
