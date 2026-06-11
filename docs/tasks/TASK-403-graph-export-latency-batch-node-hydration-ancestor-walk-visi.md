---
id: TASK-403
title: "Graph export latency \u2014 batch node hydration + ancestor walk; visible loading states"
swimlane: "graph_os"
kind: bug
epic: null
labels: [graph-os, performance, hub-ui, ready]
status: complete
priority: P1
appetite: 4h
created: 2026-06-11
started: 2026-06-11
completed: 2026-06-11
agent_session: ses-claude-20260611-002926-83d4
depends_on: []
blocked_by: []
references: []
---
# TASK-403: Graph export latency — batch node hydration + ancestor walk; visible loading states

---
id: TASK-403
title: "Graph export latency — batch node hydration + ancestor walk; visible loading states"
swimlane: "graph_os"
kind: bug
epic: null
labels: [graph-os, performance, hub-ui, ready]
status: icebox
priority: P1
appetite: 4h
created: 2026-06-11
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-403: Graph export latency — batch node hydration + ancestor walk; visible loading states

**Outcome (one sentence):** The Graph tab loads interactively at enterprise scale: the export blend hydrates nodes with batched IN-queries instead of one get_node round-trip per uid and the spine-connectivity ancestor walk is set-wise, cutting the spine sidebar produce from ~12-30s to well under 2s on this repo (and scaling linearly for 3x repos); the canvas shows a prominent centered loading state while a fetch is in flight so slow responses never read as a frozen tab.

## Read First
- src/core/graph_os/tools/graph.py
- src/core/graph_os/backends/sqlite_backend.py
- src/core/web/ui/src/features/graph/GraphCanvas.tsx
- src/core/web/_cache.py

## Repro Steps
1. After TASK-402 raised the export budget, open Hub → Graph: the spine sidebar request (contains, max_nodes=30000) takes ~12-30 s; the sidebar shows "loading spine…" and depth/budget toggles feel dead until it lands (2026-06-11 screenshot).
2. Measured baseline: cache-busted spine export = 12.2 s for 2,698 nodes; the blend hydrates ~30k node uids via one get_node round-trip each and walks contains-ancestors per node.
Expected: interactive (<2 s) and an obvious in-flight indicator. Actual: ~12-30 s of apparent freeze on first load and after every reindex (signature cache bust).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the spine sidebar export (contains, 30k budget, exclude list), **When** produced cold (cache-busted), **Then** it returns in under 2 s on this repo and node hydration uses batched IN-queries (no per-uid loop).
- **Given** the canvas with any fetch in flight, **When** the user looks at the tab, **Then** a prominent centered loading overlay is visible (not just a tiny corner chip).
- **Given** the perf changes, **When** targeted graph tests + the smart-export suite run, **Then** green with identical payload semantics.

## Work Log
- 2026-06-11 [claude]: Edit sqlite_backend.py
- 2026-06-11 [claude]: Edit graph.py
- 2026-06-11 [claude]: Edit graph.py
- 2026-06-11 [claude]: Edit graph.py
- 2026-06-11 [claude]: Edit graph.py
- 2026-06-11 [claude]: Edit graph.py
- 2026-06-11 [claude]: Edit GraphCanvas.tsx
- 2026-06-11 [claude]: Latency root causes: per-uid get_node hydration (~30k round trips) + per-node _contains_ancestors walks in _export_blend
- 2026-06-11 [claude]: Status transitioned to complete via cos task-done.
