---
id: TASK-114
title: "Fix enforce-anti-ambiguity dead gate — wire cos_ambiguity_check to write the cache marker + exit 2"
swimlane: core
kind: bug
epic: hook-remediation
labels: [hooks, cognition, audit-n10]
status: icebox
priority: P1
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-114: Fix enforce-anti-ambiguity dead gate — wire cos_ambiguity_check to write the cache marker + exit 2

**Outcome (one sentence):** cos_ambiguity_check writes .ambiguity-cache (PASS / FAIL:criteria) via the panel state path on the EXECUTE-phase check; enforce-anti-ambiguity uses exit 2 to BLOCK so the gate provides real enforcement consistent with the cognition layer.

## Read First
- src/core/hooks/enforce-anti-ambiguity.sh
- src/core/thinking_os/tools/cognition.py

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
