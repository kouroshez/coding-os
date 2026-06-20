---
id: TASK-473
title: "Logging + routing correctness \u2014 durable floor decoupling (P4-2) + per-role model attribution (P4-9)"
swimlane: infra
kind: bug
epic: null
labels: [logging-os, routing, audit-pass4, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-20
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-473: Logging + routing correctness — durable floor decoupling (P4-2) + per-role model attribution (P4-9)

**Outcome (one sentence):** COS_LOG_DB_MIN_LEVEL becomes the authoritative durability floor independent of the console floor COS_LOG_LEVEL (per-sink flooring), and the routing learning loop attributes a role's outcome to the model that actually ran the role (formula_dispatches.model), not the orchestrator's session model (task_outcomes.model). Closes two correctness defects B-4's population fix exposed.

## Read First
- src/core/logging_os/api.py
- src/core/hooks/cos-env.sh
- src/core/thinking_os/tools/routing.py
- src/core/thinking_os/tools/record_outcome.py

## Repro Steps
COS_LOG_LEVEL=ERROR COS_LOG_DB_MIN_LEVEL=WARN; cos_say WARN demo → 0 log_events rows (console floor short-circuits at cos-env.sh:755 / api.py:25 before the DB floor). routing.py:91-99 reads task_outcomes.model (= orchestrator model via record_outcome.py:164), never formula_dispatches.model (the true per-role model at cognition.py:1117).

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** COS_LOG_LEVEL=ERROR + COS_LOG_DB_MIN_LEVEL=WARN and a session run under Opus that dispatched a role to Sonnet **When** a WARN is emitted through api._emit/cos_say and route_model later ranks for that complexity **Then** exactly one durable log_events row is written with no stderr line, AND route_model credits Sonnet (the per-role model) not Opus; AND regression tests cover both the console>db floor regime and the per-role attribution; AND thinking_os + logging_os matrix suites pass.

## Work Log
