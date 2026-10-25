---
id: TASK-1073
title: "Index files changed outside the agent at session start instead of a nightly reindex"
swimlane: infra
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
# TASK-1073: Index files changed outside the agent at session start instead of a nightly reindex

**Outcome (one sentence):** Opening a session re-indexes only the files that changed since the last indexed commit (git pull, branch switch, edits made outside the agent) in the background, and doctor grades graph freshness by whether the index matches the tree, not by its age.

## Read First
- docs/engineering/graph_os-queries.md
- src/core/hooks/_reindex_on_edit.sh
- src/cli/_doctor_graph_pipeline.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a file added by git pull since the last session, **When** a session starts, **Then** that file's nodes appear in the graph without cos graph-reindex.
- **Given** a file deleted outside the agent, **When** a session starts, **Then** its nodes are pruned.
- **Given** no change since the last indexed commit, **When** a session starts, **Then** no reindex worker is spawned and the hook stays under 200ms.
- **Given** an index untouched for 3 days on an unchanged tree, **When** cos doctor runs, **Then** graph.freshness passes.

## Work Log
- 2026-10-24 [claude]: warn-graph-empty now catches the graph up at SessionStart: git diff since .graph-indexed-head +…
- 2026-10-24 [claude]: Reverted in 0872a10e: the session-start catch-up forked a detached reindex worker per session start; my ~20 timing…
