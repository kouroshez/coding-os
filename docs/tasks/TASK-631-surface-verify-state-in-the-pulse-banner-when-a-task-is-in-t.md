---
id: TASK-631
title: "Surface verify-state in the pulse/banner when a task is in testing (low priority)"
swimlane: core
kind: feature
epic: null
labels: [ready]
status: archive
priority: P3
appetite: 1d
created: 2026-06-27
started: 2026-06-27
completed: 2026-06-27
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-631: Surface verify-state in the pulse/banner when a task is in testing (low priority)

**Outcome (one sentence):** session-context.sh surfaces the recorded matrix-suite verify-state (from .last-verify.json) in the agent pulse, but ONLY when the current task is in `testing` status, so the agent sees whether the close-gate suite is fresh without paying banner token cost on every turn.

## Read First
- src/core/hooks/session-context.sh
- src/core/board_os/verify_suites_cli.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the current task is in testing AND .last-verify.json has a recent PASS **When** the pulse renders **Then** it shows verify=<suite>. - **Given** the task is not in testing **When** the pulse renders **Then** no verify field (no token cost). - **Given** no .last-verify.json **Then** the field is omitted gracefully.

## Work Log
- 2026-06-28 [claude]: Edit session-context.sh
- 2026-06-28 [claude]: Implemented in the agent-facing pulse (PARTS, not the user banner): session-context.sh now reads .last-verify.json…
- 2026-06-28 [claude]: committed 63c17a8b · 7 files
