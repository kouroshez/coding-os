---
id: TASK-102
title: "E1: install logging_os stdlib bridge in web server + cos CLI (+ verify MCP server) — capture the 2 blind processes"
swimlane: infra
kind: feature
epic: observability-eye
labels: [observability, logging_os, bridge, ready]
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
# TASK-102: E1: install logging_os stdlib bridge in web server + cos CLI (+ verify MCP server) — capture the 2 blind processes

**Outcome (one sentence):** web/server.py create_app() and cli/main.py entrypoint call logging_os.setup() so every web-route 500 and every cos doctor/health/CLI stdlib error routes into the eye; MCP server.py bridge confirmed. A forced web 500 and a forced CLI logger.error both land in .cos.log.jsonl.

## Read First
- docs/engineering/observability-eye.md
- src/core/logging_os/config.py
- src/core/web/server.py
- src/cli/main.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the web FastAPI app is constructed via create_app(), **When** the app starts, **Then** logging_os.setup() has installed the stdlib bridge so a stdlib logger.error / uncaught route 500 is emitted through the eye (lands in .cos.log.jsonl).
- **Given** the cos CLI is invoked (any command via the click group), **When** the group callback runs, **Then** logging_os.setup() has installed the stdlib bridge so a stdlib logger.error from doctor/health/any CLI path routes into the eye.
- **Given** the MCP thinking_os server, **When** it boots, **Then** the existing logging_os.setup() bridge install is confirmed present (server.py:30) — no change needed, verified only.
- **Given** all three entrypoints, **When** the install is idempotent (called once per process), **Then** re-running setup() does not duplicate the root handler (install_bridge removes a prior bridge handler before adding).

## Work Log
- 2026-06-05 [claude]: E1 done: added idempotent logging_os.setup() to web create_app() (from logging_os) and cli/main.py group callback (from 
