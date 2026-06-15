---
id: TASK-428
title: "Hub stale-code guard: detect in cos hub status + cos doctor, auto-restart on cos update"
swimlane: infra
kind: feature
epic: null
labels: [hub, graph, consumer-ux, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-15
started: 2026-06-15
completed: 2026-06-15
agent_session: ses-claude-20260615-014142-5969
depends_on: []
blocked_by: []
references: []
---
# TASK-428: Hub stale-code guard: detect in cos hub status + cos doctor, auto-restart on cos update

**Outcome (one sentence):** Consumers never face a graph (or other in-process core) error from a long-running Hub serving pre-fix code. The Hub imports graph_os/web/thinking_os/board_os in-process and Python never reloads a live module, so a core fix only reaches projects on restart. Add a shared staleness signal (newest core *.py mtime > hub.pid mtime) surfaced in `cos hub status` and a new `hub.code_fresh` doctor check (WARN), and auto-restart a stale running Hub at the end of a non-dry-run `cos update`.

## Read First
- src/cli/hub_commands.py
- src/cli/update.py
- src/cli/doctor.py
- docs/engineering/hub-architecture.md

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** a Hub started before a core `*.py` edit **When** `cos hub status` runs **Then** it prints a stale-code warning that names `cos hub restart`.
- **Given** the same stale state **When** `cos doctor` runs **Then** a new `hub.code_fresh` check is WARN; it is PASS when the Hub is fresh or not running (no false warning).
- **Given** a stale running Hub **When** `cos update` completes (non-dry-run) **Then** the Hub is auto-restarted so every project's Graph tab + `cos_*` tools serve the new code.
- **Given** no Hub running **When** `cos hub status` or `cos doctor` runs **Then** the staleness signal is PASS and never falsely flags.

## Work Log
- 2026-06-15 [claude]: Edit hub-architecture.md
- 2026-06-15 [claude]: Edit hub-architecture.md
- 2026-06-15 [claude]: Edit hub_commands.py
- 2026-06-15 [claude]: Edit hub_commands.py
- 2026-06-15 [claude]: Edit doctor.py
- 2026-06-15 [claude]: Edit doctor.py
- 2026-06-15 [claude]: Edit update.py
- 2026-06-15 [claude]: Edit test_hub_staleness.py
- 2026-06-15 [claude]: Root cause: Hub (PID 3113, started 22h pre-fix) served stale in-process graph_os → every project's Graph tab showed `unk
- 2026-06-15 [claude]: Status transitioned to complete via cos task-done.
