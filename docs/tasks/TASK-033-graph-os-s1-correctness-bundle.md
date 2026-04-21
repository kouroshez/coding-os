---
id: TASK-033
title: "graph-os S1 correctness bundle"
swimlane: graph-os
kind: bug
epic: graph-os-redesign
labels: [correctness, concurrency, schema]
status: in_progress
priority: P2
appetite: "1d"
created: 2026-04-21
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-033: graph-os S1 correctness bundle

**Outcome:** 9 correctness bugs (B1, B2, B3, B4, B5, B6, B7, B11, B17) fixed; `make verify` green; concurrency test added.

## Read First
- [docs/roadmap/graph-os-redesign.md § S1](../roadmap/graph-os-redesign.md) — authoritative scope

## Acceptance
- **Given** the bug list in roadmap S1
- **When** S1 checkboxes all ticked
- **Then** `make verify` green, `test_concurrency.py` passes on both backends, migration v13 applied append-only

## Work Log
