---
id: TASK-762
title: "memory-v2 P4: Memory tab narrative - validation-based headline, tier separation, lesson evidence"
swimlane: core
kind: feature
epic: memory-v2
labels: [memory, hub, ready]
status: archive
priority: P3
appetite: 1d
created: 2026-07-02
started: 2026-07-02
completed: 2026-07-02
agent_session: ses-system-auto-archive
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
- 2026-07-02 [claude]: Edit patterns.py
- 2026-07-02 [claude]: Edit patterns.py
- 2026-07-02 [claude]: Edit patterns.py
- 2026-07-02 [claude]: Edit patterns.py
- 2026-07-02 [claude]: P4 complete: /api/patterns/roi gains validations_30d + helpful_rate_30d (headline prefers direct outcome evidence,…
- 2026-07-02 [claude]: Status transitioned to complete via cos task-done.
