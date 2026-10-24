---
id: TASK-1068
title: "feat(graph_os): duplicate-code ratchet fails verify on a new clone group"
swimlane: "graph_os"
kind: feature
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-10-24
started: 2026-10-24
completed: 2026-10-24
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1068: feat(graph_os): duplicate-code ratchet fails verify on a new clone group

**Outcome (one sentence):** Copy-paste stops growing: a ratchet records today's clone groups as the baseline, fails when a change adds a new group, and lowers the baseline when groups are removed.

## Read First
- docs/engineering/graph_os-queries.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the recorded baseline **When** a change adds a new exact or renamed clone group **Then** the ratchet exits non-zero naming the new group
- **Given** a group is deleted **When** the ratchet runs with --update **Then** the baseline shrinks and never grows

## Work Log
- 2026-10-24 [claude]: Status transitioned to complete via cos task-done.
