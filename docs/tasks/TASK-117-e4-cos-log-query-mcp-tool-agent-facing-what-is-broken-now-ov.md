---
id: TASK-117
title: "E4: cos_log_query MCP tool — agent-facing \"what is broken now\" over log_events"
swimlane: infra
kind: feature
epic: observability-eye
labels: [observability, mcp, query, logs, ready]
status: complete
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-117: E4: cos_log_query MCP tool — agent-facing "what is broken now" over log_events

**Outcome (one sentence):** A @safe_tool cos_log_query MCP tool (meta.layer="logs") queries log_events with level floor / scope glob / since / search(LIKE on msg) / session_id / trace_id / fingerprint filters, returning the standard ok({total, rows}) envelope — so the agent can programmatically ask "what errored since X". Modeled on tools/audit.py::audit_log_query.

## Read First
- docs/engineering/observability-eye.md
- src/core/thinking_os/tools/audit.py
- src/core/thinking_os/tools/_shared.py
- src/core/thinking_os/server.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a coding-os.db with several log_events rows at mixed levels/scopes/sessions
- **When** cos_log_query is called with a level floor / scope glob / search / since filter
- **Then** it returns the ok({total,count,rows}) envelope (meta.layer="logs") with only the matching, most-recent-first rows; the level floor uses an IN-set of severities ≥ floor; server.py --test registers it; and a unit test of log_query() (level-floor, scope LIKE glob, msg search) passes

## Work Log
- 2026-06-05 [claude]: Added tools/logs.py::log_query (level-floor IN-set, scope LIKE glob, since/search/session/trace/fingerprint, ok({total,c
