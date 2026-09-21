---
id: TASK-1042
title: "cos_graph_overview: 296 lines of spec exist as a skipped test, the tool never did"
swimlane: "graph_os"
kind: feature
epic: null
labels: [parked]
status: complete
priority: P3
appetite: 1d
created: 2026-09-18
started: 2026-09-20
completed: 2026-09-20
agent_session: ses-claude-20260920-211122-bc06
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
- 2026-09-21 [claude]: Edit _graph_overview.py
- 2026-09-21 [claude]: Edit patch_overview_rank.py
- 2026-09-21 [claude]: Built it rather than retiring the spec — the 296 lines of tests define every behaviour and all 11 pass as written,…
- 2026-09-21 [claude]: Edit patch_vacuum.py
- 2026-09-21 [claude]: commit 9ae422c3ee — feat(graph): cos_graph_overview — the architecture map its 296-line spec described
- 2026-09-21 [claude]: commit e66f35e76e — feat(scheduled): reclaim dead database pages on the nightly run
- 2026-09-21 [claude]: Status transitioned to complete via cos task-done.
