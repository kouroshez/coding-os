---
id: TASK-095
title: "Orphan panel-dir GC — heartbeat-based cleanup of .coding-os/<agent>/panels"
swimlane: core
kind: chore
epic: null
labels: [hooks, gc, multi-agent, disk-hygiene, ready]
status: complete
priority: P3
appetite: "1d"
created: 2026-06-04
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-095: Orphan panel-dir GC — heartbeat-based cleanup of .coding-os/<agent>/panels

**Outcome (one sentence):** Panel dirs whose heartbeat is older than a TTL are garbage-collected (bounded, fire-and-forget) so .coding-os/<agent>/panels/ stops growing unboundedly across sessions.

## Read First
- src/core/hooks/auto-brain-decay.sh
- src/core/hooks/cos-env.sh
- docs/engineering/state-files.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a `.coding-os/<agent>/panels/<id>/` dir whose heartbeat file is older than the TTL
- **When** the SessionStart `auto-brain-decay.sh` orphan-GC block runs
- **Then** stale (TTL 86400s) and no-session orphan (TTL 3600s) panel dirs are `rm -rf`'d, while the current `$COS_PANEL_DIR` and any live panel are excluded; the sweep is bounded + fire-and-forget (`|| true`).

## Work Log
- 2026-06-06 [claude]: Status transitioned to complete via cos task-done.
