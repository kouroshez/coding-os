---
id: TASK-941
title: "feat: one output contract for the scripts and tests the agent writes"
swimlane: core
kind: feature
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-08-12
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-941: feat: one output contract for the scripts and tests the agent writes

**Outcome (one sentence):** Every script and verification run the agent authors reports in one shared vocabulary — same status markers, same failure shape, and a visible progress signal for anything long-running — so a human reads two different runs the same way.

## Read First
- src/core/skills/clean-code/SKILL.md
- src/core/rules/test-discipline.md
- src/core/rules/anti-overengineering.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the rule is in force **When** the agent writes a new script that reports status **Then** it uses the single documented marker set rather than inventing FAIL:/ERROR:/OK: variants. **Given** a run that iterates over more than a handful of units **When** it executes **Then** it emits progress (count and position), not silence until the end. **Given** the meta repo **When** the rule lands **Then** it is reachable from the clean-code skill and the always-active rule set.

## Work Log
