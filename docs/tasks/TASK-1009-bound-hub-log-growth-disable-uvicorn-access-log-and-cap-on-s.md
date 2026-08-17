---
id: TASK-1009
title: "Bound hub.log growth \u2014 disable uvicorn access log and cap on start"
swimlane: infra
kind: bug
epic: null
labels: [incident, disk, hub, ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-08-17
started: 2026-08-17
completed: null
agent_session: ses-claude-20260817-154319-10c2
depends_on: []
blocked_by: []
references: []
---
# TASK-1009: Bound hub.log growth — disable uvicorn access log and cap on start

**Outcome (one sentence):** `~/.coding-os/hub.log` stops growing without bound so the Hub can never fill the disk the way the WAL did.

## Read First
- src/core/web/server.py
- src/cli/hub_commands.py
- docs/engineering/hub-architecture.md

## Repro Steps
`~/.coding-os/hub.log` reached 65 MB with no rotation. `cos hub start` opens it with `open(log, "ab")` and `run_server()` calls `uvicorn.run()` with the default `access_log=True`. Sampling the last 20k lines: 6471 `GET /api/presence/agents` + 6279 `GET /api/presence/now` + 2346 `GET /api/cognition/chats` — the Hub UI polls on a 2.6 s tick, so the file grows ~33k lines/day forever. Every other coding-os sink is bounded (`.graph-telemetry.jsonl` rotates at 2 MB, `logging_os` truncates by line cap, `traces/` and `panels/` are GC'd by `auto-brain-decay.sh`); `hub.log` is the only unbounded one left.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** the Hub is serving its 2.6 s presence polls, **When** `run_server` starts uvicorn, **Then** no per-request access line is written to `hub.log`.
- **Given** a `hub.log` already larger than the retention cap, **When** `cos hub start` runs, **Then** the file is truncated to its tail and the reclaimed size is reported to the operator.
- **Given** that truncation, **When** an operator reads `hub.log`, **Then** the startup banner and any error tracebacks are still present — only the per-request access noise is gone.

## Work Log
- 2026-08-17 [claude]: Edit hub-architecture.md
- 2026-08-17 [claude]: Edit server.py
- 2026-08-17 [claude]: Edit hub_commands.py
- 2026-08-17 [claude]: Edit hub_commands.py
- 2026-08-17 [claude]: Edit hub_commands.py
- 2026-08-17 [claude]: Edit test_hub_log_retention.py
