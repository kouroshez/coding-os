---
id: TASK-900
title: "File-size ratchet gate: fail any non-scaffold .py above the current max, ratchet down"
swimlane: core
kind: test
epic: null
labels: [quality, refactor-prep, ready]
status: icebox
priority: P2
appetite: 2h
created: 2026-08-08
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-900: File-size ratchet gate: fail any non-scaffold .py above the current max, ratchet down

**Outcome (one sentence):** tests/test_file_size_budget.py blocks growth of god files

## Read First
- docs/governance/critical-rules.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the ratchet test with MAX at current ceiling\n- **When** any tracked non-scaffold .py exceeds it\n- **Then** the root tests/ suite fails; lowering MAX only requires shrinking files

## Work Log
