---
id: TASK-1069
title: "feat(hooks): strict graph-context gate for shared files in new projects"
swimlane: core
kind: feature
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-10-24
started: 2026-10-24
completed: 2026-10-24
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1069: feat(hooks): strict graph-context gate for shared files in new projects

**Outcome (one sentence):** In a newly scaffolded project, an edit to a shared, high-fan-in file is blocked until the agent has asked the graph who depends on it; other files keep the warn-only default.

## Read First
- docs/engineering/hooks-reference.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a new project **When** an agent edits a shared file without a prior cos_graph_context **Then** enforce-graph-context blocks with the remediation
- **Given** a non-shared file **When** it is edited **Then** the hook only warns

## Work Log
- 2026-10-24 [claude]: Status transitioned to complete via cos task-done.
