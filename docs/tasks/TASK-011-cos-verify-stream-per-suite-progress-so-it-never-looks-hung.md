---
id: TASK-011
title: "cos verify — stream per-suite progress so it never looks hung"
swimlane: infra
kind: chore
epic: null
labels: [cli, dx]
status: icebox
priority: P2
appetite: "1d"
created: 2026-05-22
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-011: cos verify — stream per-suite progress so it never looks hung

**Outcome (one sentence):** cos verify prints a live [done/total] tick as each matrix suite finishes, plus an up-front "running N suites" line, so a multi-minute run is visibly progressing instead of appearing frozen.

## Work Log
