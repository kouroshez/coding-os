---
id: TASK-985
title: "Surface-area audit \u2014 rank every always-on rule by how often it actually fires"
swimlane: infra
kind: feature
epic: honest-benchmarks
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-08-15
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-985: Surface-area audit — rank every always-on rule by how often it actually fires

**Outcome (one sentence):** Instruction density stops being defended by assertion — every always-on rule is ranked by measured blocks and citations against the tokens it occupies, so pruning becomes a data decision.

## Read First
- src/core/hooks/registry.yaml
- src/cli/doctor_tokens.py
- src/core/rules/

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** the hook-block log and the always-on rule set, **When** the audit runs, **Then** it reports per rule: tokens occupied, blocks caused, and days since the last block.
- **Given** a rule with zero blocks and zero citations over the measured window, **When** the report is read, **Then** it is named explicitly as a pruning or lazy-load candidate rather than left implicit.
- **Given** the report, **When** it is published, **Then** it states the total always-on budget and how far it sits from the stated target.

## Work Log
