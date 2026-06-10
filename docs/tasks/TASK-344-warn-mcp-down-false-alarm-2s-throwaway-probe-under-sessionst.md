---
id: TASK-344
title: "warn-mcp-down false alarm: 2s throwaway probe under SessionStart load brands a healthy MCP as DOWN for the whole session"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: testing
priority: P1
appetite: 1h
created: 2026-06-10
started: 2026-06-10
completed: null
agent_session: ses-claude-20260610-112852-603a
depends_on: []
blocked_by: []
references: []
---
# TASK-344: warn-mcp-down false alarm: 2s throwaway probe under SessionStart load brands a healthy MCP as DOWN for the whole session

**Outcome (one sentence):** SessionStart MCP probe stops false-negativing: 6s alarm + one retry, and the DOWN banner instructs the agent to verify with one real cos_health call before abandoning MCP — so a transient probe race can no longer push the whole session into raw-read token burn.

## Read First
- src/core/hooks/warn-mcp-down.sh

## Repro Steps
1. Session 2026-06-10 ses-…603a: SessionStart printed "MCP server is unreachable this session" while the hub + 20 SessionStart hooks were booting.
2. Same session, later: `cos server-start` initialize handshake answers in 0.65s and a real `cos_health` MCP call returns ok (db healthy, 46k graph nodes) — the session's actual MCP connection was alive the whole time.
Expected: no DOWN banner for a healthy server.
Actual: the throwaway probe (`perl alarm 2` despite the 5s comment) raced SessionStart load, false-negatived, and the agent avoided MCP retrieval all session (raw-read token burn).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a healthy server that answers in <6s, **When** the hook probes (marker removed), **Then** it logs ok and prints nothing (manual smoke).
- **Given** a genuinely dead launch command, **When** probed, **Then** the banner still fires and now includes the verify-first instruction.
- **Given** make verify-hooks, **When** run, **Then** green.

## Work Log
- 2026-06-10 [claude]: Edit warn-mcp-down.sh
- 2026-06-10 [claude]: Edit warn-mcp-down.sh
- 2026-06-10 [claude]: commit b84c2b9c0e — fix(cli): board attribution prefers fresh .active-session over the frozen session-id fossil
