---
id: TASK-094
title: "Fresh session attribution — MCP server reads .active-session pointer not the stale agent fossil"
swimlane: core
kind: bug
epic: null
labels: [attribution, session, multi-agent, ready]
status: complete
priority: P2
appetite: "1d"
created: 2026-06-04
started: 2026-06-04
completed: 2026-06-04
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-094: Fresh session attribution — MCP server reads .active-session pointer not the stale agent fossil

**Outcome (one sentence):** Tasks are attributed to the current session id (matching the transcript filename), not a months-stale agent-level session-id fossil; the MCP server reads a session-context-refreshed .active-session pointer.

## Read First
- src/core/thinking_os/server.py
- src/core/hooks/session-context.sh
- docs/engineering/state-files.md

## Repro Steps
1. Start a fresh session; create a task via the MCP cos_task_create.
2. Inspect the task frontmatter `agent_session`.
Expected: the current session id (e.g. ses-claude-20260604-…-4e27).
Actual: a months-stale id from $COS_AGENT_DIR/session-id (e.g. ses-claude-20260527-…) — the legacy agent-level fossil the shell side (cos-env.sh:222) deliberately refuses to read.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** session-context.sh has run this session (writing the panel session-id)
- **When** the MCP server resolves a default agent_session via _detect_agent_session_default
- **Then** it reads the fresh `$COS_AGENT_DIR/.active-session` pointer (refreshed each prompt) rather than the stale `session-id` fossil, falling back to the per-process synth only when no pointer exists — so attribution matches the live session (and the T5.1 transcript filename). Concurrent-panel ambiguity (last-active-panel) is documented in state-files.md.

## Work Log
- 2026-06-04 [claude]: session-context.sh refreshes $COS_AGENT_DIR/.active-session each prompt; server.py + board_commands.py resolvers now rea
