---
id: TASK-141
title: "Hub Graph tab — multi-view + smart export + hierarchical layout"
swimlane: graph-os
kind: feature
epic: null
labels: []
status: complete
priority: P1
appetite: "1d"
created: 2026-04-26
started: 2026-04-25
completed: 2026-04-25
agent_session: null
depends_on: []
blocked_by: []
references: []
---
# TASK-141: Hub Graph tab — multi-view + smart export + hierarchical layout

**Outcome (one sentence):** Hub Graph tab renders the full repo as an organized brain — three view modes (Containment dagre tree, Dependencies force-directed with community coloring, Processes Louvain clusters with entry-point highlights), smart backend defaults that surface semantic edges instead of just contains, noise-free canvas (frontmatter keys hidden), and Inspector wired to tree-row clicks.

## Read First
- [core/web/ui/src/features/graph/GraphCanvas.tsx](../../core/web/ui/src/features/graph/GraphCanvas.tsx) — current canvas (ForceAtlas2 only).
- [core/web/ui/src/features/graph/ContainsTree.tsx](../../core/web/ui/src/features/graph/ContainsTree.tsx) — left tree; root selection currently disconnected from Inspector.
- [core/graph_os/tools/graph.py](../../core/graph_os/tools/graph.py) — `cos_graph_export` returns 100 contains-only edges by default; needs smart blending.
- [core/web/routes/graph.py](../../core/web/routes/graph.py) — HTTP wrapper.
- [core/graph_os/communities.py](../../core/graph_os/communities.py) (TASK-075) and [core/graph_os/entry_points.py](../../core/graph_os/entry_points.py) (TASK-081) — already produce the data the UI needs but isn't reading.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the user opens `/graph` with no root selected
- **When** the SPA bootstraps
- **Then** the canvas renders a meaningful overview — semantic edges (imports + calls + handles_*) dominate, frontmatter / heading nodes are hidden, and the layout shows clusters not a single hairball.
- **Given** the user clicks the **Containment** view tab
- **When** the canvas re-renders
- **Then** the layout is a top-down dagre tree (folder → file → class → method).
- **Given** the user clicks the **Dependencies** view tab
- **When** the canvas re-renders
- **Then** ForceAtlas2 shows nodes coloured by Louvain community with entry points drawn larger and ringed.
- **Given** the user clicks the **Processes** view tab
- **When** the canvas re-renders
- **Then** Louvain communities appear as labelled groups; clicking a process header re-roots the canvas on that community's anchor.
- **Given** the user clicks a row in the left Contains spine
- **When** the row is selected
- **Then** the right Inspector opens for that uid.
- **Given** existing tests
- **When** the new code lands
- **Then** every existing graph-os / cli / adapter / hook test still passes.

## Work Log

- 2026-04-26 — Five-priority sweep shipped end-to-end:
  - **P1 backend smart-export** in [core/graph_os/tools/graph.py](../../core/graph_os/tools/graph.py).
    `cos_graph_export(mode=…, exclude_kinds=…)` with four modes
    (`auto`/`containment`/`dependencies`/`processes`) and a closed
    noise filter (frontmatter / heading kinds default-hidden). The
    auto blend partitions the budget across `_AUTO_BLEND_BUCKETS`
    so the result is never dominated by one edge type.  HTTP +
    MCP wrappers updated in [core/web/routes/graph.py](../../core/web/routes/graph.py)
    and [core/thinking_os/server.py](../../core/thinking_os/server.py).
  - **P2 multi-view tabs** — new [core/web/ui/src/features/graph/view-mode-tabs.tsx](../../core/web/ui/src/features/graph/view-mode-tabs.tsx)
    + `viewMode` slot on the zustand store + wiring in
    [core/web/ui/src/pages/GraphPage.tsx](../../core/web/ui/src/pages/GraphPage.tsx).
  - **P3 Inspector wiring** — `setRoot` in
    [core/web/ui/src/store/graph-store.ts](../../core/web/ui/src/store/graph-store.ts)
    now mirrors the picked uid into `selectedNodeUid`, so clicking
    a row in the Contains spine opens the Inspector for it (was
    previously stuck on the placeholder).
  - **P4 noise filter on canvas** — client-side belt-and-suspenders
    in [core/web/ui/src/features/graph/graph-adapter.ts](../../core/web/ui/src/features/graph/graph-adapter.ts)
    drops frontmatter / heading nodes before they ever reach Sigma.
    Plus `normalizeKind` in [core/web/ui/src/lib/node-colors.ts](../../core/web/ui/src/lib/node-colors.ts)
    so legacy colon-prefixed kinds (`code:function`, `doc:heading`)
    map to the canonical short forms — fixed the "no nodes
    reachable" empty state that hit when visibleKinds had short
    forms but the API returned long forms.
  - **P5 dagre hierarchical layout** — new
    [core/web/ui/src/features/graph/dagre-layout.ts](../../core/web/ui/src/features/graph/dagre-layout.ts)
    used by `useSigma` when `viewMode === 'containment'`. Top-down
    orientation (rankdir=TB), independent x/y scaling so siblings
    don't squash onto one line.
  - Bug also caught + fixed: empty-string `root_uid` from the SPA
    triggered an empty BFS at the route layer.  Both the route
    (treats `""` as None) and the SPA (omits the param when no root)
    are hardened.
- Tests: [core/graph_os/tests/test_smart_export.py](../../core/graph_os/tests/test_smart_export.py)
  — 11 cases covering mode validation (rejects garbage), auto blend
  includes semantic edges, default mode is auto, noise filtered by
  default, containment-only, dependencies excludes contains,
  processes returns synthetic community nodes, exclude_kinds=[]
  disables filter, custom exclude_kinds, root-walk path unchanged.
- Verification:
  - `pytest core/graph_os/tests/ -q` → **624 passed / 3 skipped**
    (was 613 → +11 net new). Zero regressions.
  - `pytest tests/test_cli.py tests/test_adapters.py
    tests/test_adapter_parity.py -q` → 96 passed.
  - `make verify-hooks` → green.
  - `make ui-build` → tsc strict pass + 2057 modules transformed.
  - Live API: each mode returns the expected shape — auto: 273
    diversified edges across 7 types; containment: 112 contains-only;
    dependencies: 300 semantic-only; processes: 80 nodes with 3
    community labels and 77 member_of_community edges.
  - Browser smoke: all four tabs render distinct meaningful views,
    Inspector opens with breadcrumbs / neighbours / kind / file path
    when the user picks a tree row, Containment lays out as a proper
    top-down dagre tree.

