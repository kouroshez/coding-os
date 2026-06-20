---
id: TASK-489
title: "Graph-aware PR/diff triage view in the Hub on the existing cos_graph_diff kernel"
swimlane: core
kind: feature
epic: null
labels: [hub, review, deferred, ready]
status: complete
priority: P3
appetite: 1d
created: 2026-06-20
started: 2026-06-20
completed: 2026-06-20
agent_session: ses-claude-20260620-144553-a8b6
depends_on: [TASK-488]
blocked_by: []
references: []
---
# TASK-489: Graph-aware PR/diff triage view in the Hub on the existing cos_graph_diff kernel

**Outcome (one sentence):** A Hub view takes a base..head range and shows changed symbols → downstream consumers/tasks → a coarse risk level, built on the existing cos_graph_diff kernel (no new diff engine), giving reviewers graph-aware blast-radius at review time. Deferred: most valuable once a PR-ingestion feed (GitHub App / CI) exists; until then it serves manual range entry.

## Read First
- src/core/graph_os/tools/graph.py
- src/core/web/routes/graph.py
- src/core/web/ui/src/

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** cos_graph_diff (graph.py:4279, delegating to detect_changes) already computes changed-symbol → downstream impact and the /diff HTTP route is delivered by TASK-488, **When** a reviewer enters a base..head range in the Hub, **Then** a thin view renders changed symbols, downstream_consumers, downstream_tasks, and risk_level by consuming the /diff route with no new kernel. **And** walk_truncated is surfaced honestly when the impact walk hits its visit cap. **And** risk_level is labelled heuristic (edge-count thresholds), never an authoritative score. **And** the view degrades gracefully when no PR-ingestion feed exists (manual range entry still works).

## Work Log
- 2026-06-20 [claude]: Edit DiffTriagePanel.tsx
- 2026-06-20 [claude]: Edit NodeInspector.tsx
- 2026-06-20 [claude]: Edit NodeInspector.tsx
- 2026-06-20 [claude]: Edit NodeInspector.tsx
- 2026-06-20 [claude]: Edit DiffTriagePanel.test.tsx
- 2026-06-20 [claude]: Added DiffTriagePanel.tsx — a thin Hub view that takes a base..head range, consumes the /api/graph/diff route…
- 2026-06-20 [claude]: committed f11dab2c · 3 files
