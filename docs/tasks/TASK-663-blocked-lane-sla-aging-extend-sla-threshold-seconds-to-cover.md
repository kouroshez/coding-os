---
id: TASK-663
title: "Blocked-lane SLA aging \u2014 extend _sla_threshold_seconds to cover 'blocked' + blocked_sla_hours knob so stale blocked tasks surface"
swimlane: "board_os"
kind: feature
epic: blocked-lane-management
labels: [blocked, sla, staleness, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-30
started: 2026-06-30
completed: 2026-06-30
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-663: Blocked-lane SLA aging — extend _sla_threshold_seconds to cover 'blocked' + blocked_sla_hours knob so stale blocked tasks surface

**Outcome (one sentence):** A task dwelling in 'blocked' beyond a configurable blocked_sla_hours threshold is reported stale=True by _flag_stale (today _sla_threshold_seconds maps only in_progress/testing/icebox, so blocked is always stale=False), and surfaces in board/daily as an aging-blocked signal — never auto-escalated to the emergency lane.

## Read First
- src/core/board_os/mcp_tools.py
- src/core/board_os/transition_gates.py
- .coding-os/scrumban-config.yaml
- docs/governance/task-lifecycle.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a task blocked longer than blocked_sla_hours, **When** cos_task_board or daily computes staleness, **Then** _flag_stale reports stale=True with a blocked-specific stale_reason.
- **Given** a task blocked under the threshold, **When** staleness is computed, **Then** stale=False.
- **Given** blocked_sla_hours set in scrumban-config.yaml, **When** the threshold is read, **Then** the configured value is honored with no hardcode, and an absent config falls back to a documented default.
- **Given** an aging blocked task, **When** it is flagged, **Then** it is only surfaced in board/daily, never auto-moved to emergency.

## Work Log
- 2026-07-01 [claude]: _sla_threshold_seconds maps 'blocked'->workflow_policy.blocked_sla_hours (default 72h, config-driven, 0 disables);…
- 2026-07-01 [claude]: committed fc8c5d1a · 5 files
- 2026-07-01 [claude]: Status transitioned to complete via cos task-done.
