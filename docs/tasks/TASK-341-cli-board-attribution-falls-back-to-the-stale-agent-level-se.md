---
id: TASK-341
title: "CLI board attribution falls back to the stale agent-level session-id fossil \u2014 .active-session skipped without env"
swimlane: cli
kind: bug
epic: null
labels: [ready]
status: archive
priority: P1
appetite: 2h
created: 2026-06-10
started: 2026-06-10
completed: 2026-06-10
agent_session: ses-claude-20260610-112852-603a
depends_on: []
blocked_by: []
references: []
---
# TASK-341: CLI board attribution falls back to the stale agent-level session-id fossil — .active-session skipped without env

**Outcome (one sentence):** cos task-create/move/done from a plain shell attribute to the CURRENT panel session (.active-session, refreshed every prompt), never the frozen .coding-os/<agent>/session-id fossil — fixing per-session WIP counting, zombie reclaim, assign-guard, and board attribution for all CLI-driven mutations.

## Read First
- src/cli/board_commands.py
- src/core/board_os/_agent_runtime.py

## Repro Steps
1. In an agent Bash shell (no COS_AGENT_DIR/COS_PANEL_DIR exported), run `cos task-create …` while `.coding-os/claude/session-id` holds a weeks-old id (mtime 2026-05-27) and `.coding-os/claude/.active-session` holds today's.
2. Inspect the created task frontmatter / task_status_history row.
Expected: agent_session = today's session (ses-claude-20260610-…-603a).
Actual: agent_session = the 2026-05-27 fossil (TASK-337..340 all carry it) — `_agent_session_id()` only consults `.active-session` when `$COS_AGENT_DIR` is exported, which plain shells never have.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** no COS_* env vars and a stale .coding-os/claude/session-id plus a fresh .coding-os/claude/.active-session, **When** _agent_session_id() resolves, **Then** it returns the .active-session value (unit test).
- **Given** COS_AGENT_SESSION_ID or a panel session-id, **When** resolving, **Then** existing precedence is unchanged (tests stay green).
- **Given** tests/test_cli.py, **When** run, **Then** green.

## Work Log
- 2026-06-10 [claude]: Edit board_commands.py
- 2026-06-10 [claude]: Edit test_board_commands_agent_detect.py
- 2026-06-10 [claude]: Edit test_board_commands_agent_detect.py
- 2026-06-10 [claude]: Edit board_commands.py
- 2026-06-10 [claude]: Edit board_commands.py
- 2026-06-10 [claude]: Edit mcp_time_probe.py
- 2026-06-10 [claude]: Edit TASK-344-warn-mcp-down-false-alarm-2s-throwaway-probe-under-sessionst.md
- 2026-06-10 [claude]: committed b84c2b9c: src/cli/board_commands.py, tests/test_board_commands_agent_detect.py
- 2026-06-10 [claude]: Status transitioned to complete via cos task-done.
