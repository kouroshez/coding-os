---
id: TASK-1042
title: "cos_graph_overview: 296 lines of spec exist as a skipped test, the tool never did"
swimlane: "graph_os"
kind: feature
epic: null
labels: [parked]
status: icebox
priority: P3
appetite: 1d
created: 2026-09-18
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1042: cos_graph_overview: 296 lines of spec exist as a skipped test, the tool never did

**Outcome (one sentence):** Either `cos_graph_overview` exists and its 296 lines of already-written tests run, or the spec is retired deliberately — not left as a skip that has quietly inflated the suite count since May.

## Read First
- src/core/graph_os/tests/test_brain_overview.py (the spec already exists, as a test)
- src/core/graph_os/tools/graph.py
- docs/engineering/graph-hallucination-cures.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** `cos_graph_overview` registered in `graph_os.tools.graph`
**When** `test_brain_overview.py` runs
**Then** all 11 tests execute and pass — no `hasattr` skip remains.

**Given** the decision instead goes the other way
**When** the spec is retired
**Then** the test file is deleted in the same commit that records why, so the
suite count stops carrying 11 tests that never ran.

## Work Log
