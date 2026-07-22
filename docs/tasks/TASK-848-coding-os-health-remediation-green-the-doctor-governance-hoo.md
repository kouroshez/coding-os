---
id: TASK-848
title: "coding-os health remediation: green the doctor (governance \u2014 hooks, doctor-config, graph/state)"
swimlane: core
kind: chore
epic: null
labels: []
status: testing
priority: P2
appetite: 1d
created: 2026-07-22
started: 2026-07-22
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-848: coding-os health remediation: green the doctor (governance — hooks, doctor-config, graph/state)

**Outcome (one sentence):** cos doctor goes from 4 FAIL / 4 WARN to green (or only-legitimate WARNs): recreate the 2 declared-but-missing memory hooks per spec, fix the non-executable hook, skip docs/tasks false-positives in the placeholder scan, prune dead hub registry entries + stale state, repair legacy graph uids.

## Work Log
- 2026-07-22 [claude]: Edit doctor-config.yaml
- 2026-07-22 [claude]: Edit doctor.py
- 2026-07-22 [claude]: Two reuse-first pivots avoided wrong fixes: (1) the '2 missing hooks' were NOT missing —…
