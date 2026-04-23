---
id: TASK-016
title: "J.1  classify_query — regex + keyword classifier"
swimlane: core
kind: feature
epic: phase-j
labels: []
status: complete
priority: P2
appetite: "1d"
created: 2026-04-20
started: 2026-04-22
completed: 2026-04-23
agent_session: ses-cursor-20260423-155740-a0e9
depends_on: []
blocked_by: []
references: []
---
# TASK-016: J.1  classify_query — regex + keyword classifier

**Outcome (one sentence):** `classify_query(query)` added with ordered regex/keyword rules and deterministic outputs (`shape`, `confidence`, `reason`) that match Phase J.1 expectations.

## Read First
- [docs/phase-j-meta-router-plan.md#j1--query-classifier](../phase-j-meta-router-plan.md) - J.1 rule order, enum contract, and confidence targets.
- [core/board_os/workflow.py](../../core/board_os/workflow.py) - existing fail-closed patterns and state transition style used across core logic.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a query that contains `TASK-016` (or any `TASK-###` token) and no higher-priority behavioral prefix,
- **When** `classify_query(query)` is called,
- **Then** it returns `shape="task_ref"` with `confidence>=0.95` and a non-empty `reason`.

- **Given** a behavioral query like "how should I move a task to ready?",
- **When** `classify_query(query)` is called,
- **Then** it returns `shape="behavioral"` and the classifier does not dispatch to retrieval layers.

- **Given** an identifier-style query containing a function-like token or code path (for example ``parse_task(...)`` or `core/...`),
- **When** `classify_query(query)` is called,
- **Then** it returns `shape="identifier"` with a grep-oriented reason string suitable for routing hints.

## Work Log
- 2026-04-23 [cursor]: Status transitioned to complete via cos task-done.
