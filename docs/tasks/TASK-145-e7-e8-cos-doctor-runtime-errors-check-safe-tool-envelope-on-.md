---
id: TASK-145
title: "E7+E8: cos doctor runtime-errors check + @safe_tool envelope on cos_task_show / cos_task_move"
swimlane: infra
kind: feature
epic: observability-eye
labels: [observability, doctor, mcp, ready]
status: complete
priority: P2
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-145: E7+E8: cos doctor runtime-errors check + @safe_tool envelope on cos_task_show / cos_task_move

**Outcome (one sentence):** cos doctor gains a runtime.recent_errors check that WARN/FAILs when the durable WARN+ error rate in a window crosses a threshold (so a project actively throwing errors no longer reports exit=0 healthy); and cos_task_show / cos_task_move are wrapped with @safe_tool so an uncaught exception returns a typed fail() envelope (logged) instead of a raw MCP protocol error.

## Read First
- docs/engineering/observability-eye.md
- src/cli/doctor.py
- src/core/board_os/mcp_tools.py
- src/core/thinking_os/tools/logs.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a coding-os.db whose log_events holds recent ERROR/FATAL rows
- **When** cos doctor runs (and an exception is forced inside cos_task_show)
- **Then** a runtime.recent_errors check reports WARN (ERROR) or FAIL (FATAL) and feeds the strict exit code; cos_task_show/cos_task_move return a fail() envelope on an uncaught error (now @safe_tool-wrapped); and doctor + board tests are green

## Work Log
- 2026-06-05 [claude]: E7: doctor _check_runtime_errors (reuses log_query) appended to run_doctor — FAIL on FATAL, WARN on ERROR>=threshold in 
