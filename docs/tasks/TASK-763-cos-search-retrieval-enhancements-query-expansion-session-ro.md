---
id: TASK-763
title: "cos_search retrieval enhancements: query expansion + session round-robin (deferred)"
swimlane: core
kind: feature
epic: memory-v2
labels: [memory, deferred]
status: archive
priority: P3
appetite: 1d
created: 2026-07-02
started: null
completed: null
agent_session: ses-claude-20260702-023419-c2e8
depends_on: []
blocked_by: []
references: []
---
# TASK-763: cos_search retrieval enhancements: query expansion + session round-robin (deferred)

**Outcome (one sentence):** cos_search optionally expands the query into <=3 LLM-free variants and round-robins results across sessions, measured against retrieval-quality metrics before/after.

## Read First
- docs/engineering/graph_os-queries.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a query with a known synonym miss, **When** expansion is enabled, **Then** recall includes the synonym hit without exceeding 3x base cost
- **Given** results dominated by one session, **When** round-robin applies, **Then** top-k spans multiple sessions

## Work Log
