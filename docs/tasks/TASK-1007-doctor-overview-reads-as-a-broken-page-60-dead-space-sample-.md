---
id: TASK-1007
title: "Doctor Overview reads as a broken page: 60% dead space, sample counts that look like totals"
swimlane: core
kind: bug
epic: null
labels: [ui, design, diagnostics, readme, ready]
status: icebox
priority: P3
appetite: 1d
created: 2026-08-17
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1007: Doctor Overview reads as a broken page: 60% dead space, sample counts that look like totals

**Outcome (one sentence):** The Diagnostics → Doctor Overview tab is worth screenshotting: no half-empty viewport, no stat that reads as a total when it is a probe sample, no two panels restating the same three numbers, and no page-level OK pill sitting under a header warning.

## Read First
- src/core/web/ui/src/pages/DoctorPage.tsx
- src/core/web/ui/src/features/graph/GraphCanvas.tsx
- docs/engineering/hub-architecture.md

## Repro Steps
Open http://127.0.0.1:9188/p/coding-os/diagnostics/doctor at 1600x1000. Content stops ~60% up the viewport; the rest is empty. The stat cards read `NODES (SAMPLE) 101` and `EDGES (SAMPLE) 100` while `cos_graph_export` reports `graph_node_total=78128` for the same graph. `INDEX FRESHNESS` and `PROBE SAMPLE` both print rows=4827 / node count / edge count. The page pill says `DOCTOR · OK` while the app header simultaneously shows `⚠ 1 graph issue`.

## Acceptance (G/W/T) — *this IS the Definition of Done*

1. **Given** the Doctor Overview at 1600x1000 **When** it renders **Then** content fills the viewport, or the layout stops reserving space it never uses.
2. **Given** a probe sample of 101 nodes on a 78,128-node graph **When** the stat card renders **Then** its label cannot be read as the size of the graph.
3. **Given** INDEX FRESHNESS and PROBE SAMPLE **When** both render **Then** no number appears in both panels.
4. **Given** the header reports a graph issue **When** the page pill renders **Then** the two do not contradict each other on the same screen.

## Work Log
