---
id: TASK-095
title: "Orphan panel-dir GC — heartbeat-based cleanup of .coding-os/<agent>/panels"
swimlane: core
kind: chore
epic: null
labels: [hooks, gc, multi-agent, disk-hygiene, ready]
status: icebox
priority: P3
appetite: "1d"
created: 2026-06-04
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-095: Orphan panel-dir GC — heartbeat-based cleanup of .coding-os/<agent>/panels

**Outcome (one sentence):** Panel dirs whose heartbeat is older than a TTL are garbage-collected (bounded, fire-and-forget) so .coding-os/<agent>/panels/ stops growing unboundedly across sessions.

## Work Log
