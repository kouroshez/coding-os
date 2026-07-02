---
id: TASK-762
title: "memory-v2 P4: Memory tab narrative - validation-based headline, tier separation, lesson evidence"
swimlane: core
kind: feature
epic: memory-v2
labels: [memory, hub, ready]
status: icebox
priority: P3
appetite: 1d
created: 2026-07-02
started: null
completed: null
agent_session: null
depends_on: [TASK-759]
blocked_by: []
references: []
---

# TASK-762: memory-v2 P4: Memory tab narrative - validation-based headline, tier separation, lesson evidence

**Outcome (one sentence):** Hub Memory tab leads with a validation-rate-based effectiveness headline, separates promoted/Trusted/forming lessons visually, and shows each lesson's evidence refs; producer contracts verified and api-types.ts regenerated.

## Read First
- docs/engineering/hub-architecture.md
- src/core/rules/api-contract-discipline.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** validation data exists, **When** the Memory tab loads, **Then** the headline derives from 30-day helpful-rate (not stumble bars alone)
- **Given** lessons across tiers, **When** the list renders, **Then** promoted, Trusted and forming groups are visually distinct and each lesson exposes its evidence
- **Given** the route payloads, **When** the UI builds, **Then** field names match the producer and api-types.ts is regenerated

## Work Log
