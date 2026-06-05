---
id: TASK-141
title: "E5: cos errors / cos logs CLI — human + CLI-agent access to the durable error store"
swimlane: infra
kind: feature
epic: observability-eye
labels: [observability, cli, logs, ready]
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
# TASK-141: E5: cos errors / cos logs CLI — human + CLI-agent access to the durable error store

**Outcome (one sentence):** cos errors (and cos logs) print recent durable log_events rows filtered by level/scope/since/search/limit, reusing thinking_os.tools.logs.log_query and logging_os render (rows to stdout, summary to stderr) — so a human or a CLI-driven agent can see what is broken without the MCP layer.

## Read First
- docs/engineering/observability-eye.md
- src/cli/main.py
- src/core/thinking_os/tools/logs.py
- src/core/logging_os/render.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a coding-os.db with log_events rows at mixed levels
- **When** a user runs `cos errors` (ERROR+ default) or `cos logs --level warn --scope cli.* --search X`
- **Then** matching rows render most-recent-first on stdout (via logging_os render short), a count summary goes to stderr, `--json` emits the raw envelope, an empty result prints a clear "no events" line (exit 0), and tests/test_cli.py stays green

## Work Log
- 2026-06-05 [claude]: Added src/cli/logs_commands.py (cos logs + cos errors; reuse log_query + logging_os render; dual-path imports; rows→stdo
