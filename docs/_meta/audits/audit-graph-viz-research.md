<!-- domain:ALL | layer:engineering | ssot:false | updated:2026-05-23 -->
# Audit — Code-Knowledge-Graph Visualization Research (2024-2026 SOTA)

Date: 2026-05-23
Scope: Inform redesign of `src/core/web/ui/` Sigma.js graph canvas (~40K nodes / ~100K edges, polyglot monorepo).
Pain points addressed: root node visually tiny; force-directed layout obscures hierarchy; depth presets use opaque node-cap; "max" still truncates.

## TL;DR

1. **Keep Sigma.js. Replace ForceAtlas2 as the *default* with a hybrid: ELK-layered for the containment skeleton, FA2 only inside expanded clusters.** Sigma.js is the only WebGL renderer in the JS ecosystem that survives 40K nodes at interactive frame rates — Cytoscape/vis-network cap at ~5K. The layout problem is solved with `elkjs` (compute) → Sigma (render); no library swap needed.
2. **Size nodes by `log(1 + PageRank) × kind_weight`, with the repo root pinned to the largest tier and rendered with a Linkurious-style halo.** Degree centrality alone makes hub directories dominate but underweights the conceptual root; PageRank+kind correctly elevates the `.` node, entry-points, and `__init__.py`-class hubs.
3. **Replace depth-presets-as-node-cap with depth-presets-as-BFS-radius from the focus node, plus a hard 5K-node render budget with progressive disclosure on click.** Tree-depth is the only semantic users can predict ("show me 2 hops around `foo`"); node-cap is opaque. The render budget is separate, displayed honestly, and surplus expands via click — the GitHub Next / Sourcegraph pattern.

## Layout engine matrix

| Engine | Scale (smooth) | Hierarchy quality | Sigma compat | Dev cost | Recommendation |
|---|---|---|---|---|---|
| **ForceAtlas2** (current) | 50K+ via WebWorker | Poor — no hierarchy signal, "hairball" | Native (graphology) | Low | Demote: secondary, inside clusters only |
| **Dagre** | ~5K before slow | Good for pure DAG; mangles cycles randomly; no nested clusters | Bridge via graphology-layout | Low | Reject — code graphs have cycles + need nesting |
| **ELK (elkjs)** | ~10K (layered); 40K only with hierarchical pruning | Best-in-class — supports nested clusters, layered, radial, force, mrtree, rectpacking | Compute coords offline, feed Sigma | Medium (Web Worker required, Java port is ~2MB) | **Adopt** as primary skeleton layout |
| **Radial tree (d3-hierarchy)** | 40K easily | Excellent for strict trees; breaks on multi-parent edges (imports) | Compute coords, feed Sigma | Low | Adopt as the "containment view" specialization |
| **Treemap / circle-pack (d3)** | 100K+ | Best for containment-only view (GitHub Next pattern) | Different geometry — render via Sigma node positions or D3 overlay | Low-Medium | Adopt as a *third* view mode alongside graph + tree |
| **Cola.js** | ~3K | Constraint-based — good for small subgraphs | Possible but no first-class graphology bridge | High | Reject — scale ceiling too low |
| **Hybrid (ELK skeleton + FA2 in clusters)** | 40K+ | Best practical hierarchy + readable local structure | Native | Medium | **Adopt** — this is the production pattern |

Key sources: [Sigma.js WebGL caps at 100K–500K nodes vs Canvas ~3-5K](https://www.pkgpulse.com/blog/cytoscape-vs-vis-network-vs-sigma-graph-visualization-javascript-2026); [Dagre has no nesting and randomizes cycle removal](https://reactflow.dev/examples/layout/dagre); [ELK Layered is the standard for dataflow/dependency graphs](https://eclipse.dev/elk/); [Sigma.js GitHub discussion confirms Dagre integration but recommends d3-hierarchy/elkjs for trees](https://github.com/jacomyal/sigma.js/discussions/1477).

## Sizing scheme recommendation

**Adopt: `radius = base + α · log(1 + PageRank(node)) + β · kind_weight(node) + γ · is_root_bonus`**, with a halo glow for the top-N most central nodes.

Why not degree:
- Degree privileges directories with many files. Useful for "find the hub" but misses that the repo root has *low* edge degree (one CONTAINS edge per top-level dir) while being conceptually the apex. PageRank propagates importance from descendants up to the root, which is what users perceive.
- Degree is what most naive tools default to; the result is the failure mode you reported (root tiny, leaf hubs dominant).

Why PageRank + kind_weight + root_bonus:
- **PageRank** (already computable via graphology) gives the "important hub" signal independent of fan-out direction. [Neo4j Bloom binds node size to PageRank as its canonical pattern](https://medium.com/neo4j/bloom-ing-marvellous-a2be0c3702bb) — rule-based styling on a computed property.
- **kind_weight** lets you assert domain priors: `repo_root: 3.0`, `package: 2.0`, `module: 1.5`, `class: 1.2`, `function: 1.0`, `variable: 0.7`. Codifies "a class matters more than a constant" without flattening.
- **is_root_bonus** is a hard floor — the repo root is always in the top size tier regardless of computed centrality. Required to fix the reported pain point and matches [GitHub Next repo-vis where root packs the canvas](https://githubnext.com/projects/repo-visualization/).

Visual emphasis layer (the "halo"):
- Top-20 by PageRank get a Linkurious-Ogma-style soft halo (radial gradient, 1.5× node radius, 30% opacity). [Linkurious documents `halo` as the canonical "you are connected to this" affordance](https://doc.linkurious.com/ogma/latest/examples/node-halo.html). Use it for *importance*, not selection.
- Repo root gets a permanent halo + slow pulse animation (300ms ease, 4s period). One-off rule, not a system.

Use `log(1 + x)` not raw — without log, the root would be 100× larger than its grandchildren and the periphery would vanish.

## Depth budget recommendation

**Adopt: BFS-radius semantics from a focus node + separate render budget + progressive disclosure.**

Three independent controls, each with a single honest semantic:

| Control | Semantic | UI |
|---|---|---|
| **Focus** | Which node is the center? Defaults to repo root. | Click to set; keyboard `f` to refocus on selected. |
| **Depth** | Show all nodes within K BFS hops from focus. | Discrete: 1, 2, 3, 4, "all". No "low/medium/high" — those don't predict anything. |
| **Render budget** | Hard cap on rendered nodes for FPS. Default 5000; user-bumpable to 20K with a "may stutter" warning. | Slider. Shows `2,341 / 5,000 rendered · 38 nodes hidden`. |

Progressive disclosure rule: when depth-K BFS exceeds the budget, render the K-1 frontier in full and show K's overflow as **collapsed cluster bubbles** sized by descendant count. Click a bubble → expand that branch only (re-runs ELK locally). This is the [Bloom + Sourcegraph cross-repo navigation pattern](https://sourcegraph.com/blog/cross-repository-code-navigation): lazy expansion preserves the mental model.

Why this fixes the pain:
- "Max doesn't show everything" disappears — "all" depth + a budget the user *sees and controls* is honest. Truncation is no longer silent.
- BFS-radius is what users actually mean by "how deep" — they're asking about graph distance from the thing they care about, not a population cap.
- A 40K-node monorepo at depth=2 from root typically yields 200–2000 nodes — well inside any budget, so most sessions never hit truncation at all.

This is the [Interaction Design Foundation's progressive disclosure principle](https://ixdf.org/literature/topics/progressive-disclosure) applied to a graph: show overview, reveal detail on demand.

## Migration risk assessment — Sigma.js stay vs replace

**Verdict: stay on Sigma.js. The pain points are layout + sizing + UX, not the renderer.**

| Alternative | Why not |
|---|---|
| **Cytoscape.js** | Canvas renderer caps at 3–5K smooth nodes — would *worsen* the 40K case. Richer built-in layouts don't compensate for the FPS regression. |
| **react-flow / xyflow** | Node-based UI library, not a graph renderer. Optimized for ~500–2K editable nodes (workflow diagrams). 40K-node read-only graphs are explicitly out of scope. ELK/Dagre integration is exactly what we'd be building anyway, but on a smaller-scale runtime. |
| **vis-network** | Canvas. Same scale ceiling as Cytoscape. Lower extensibility. |
| **3D (force-graph-3d, already in package.json)** | Good demo, poor production. 3D adds depth occlusion that *hurts* discoverability of hierarchy. Keep as an optional view, do not promote. |
| **D3 raw** | Build-your-own everything. Would lose Sigma's WebGL renderer. Reject unless you want a 6-month project. |

What stays the same:
- Sigma.js WebGL renderer.
- graphology data model.
- React + Vite + Zustand shell.
- `cos_graph_export` → frontend pipeline.

What changes:
- Add `elkjs` (web-worker) as the default layout computer; FA2 stays as a secondary "physics mode" toggle.
- Add `graphology-metrics` PageRank (already runs server-side via `cos_graph_ranking` — reuse, don't recompute).
- Replace `depth: low|med|high|max` enum with `{focus_uid, depth_hops: 1|2|3|4|inf, render_budget: int}`.
- Add a containment-only view mode (d3 circle-pack via Sigma node positions) toggleable from the existing dependency-view toggle.

Migration is incremental — none of the changes break the current Sigma+FA2 path; they're additive modes. Estimated effort: 2-3 task-weeks (one for layout pipeline, one for sizing+halo, one for depth-budget UX + progressive disclosure).

## Concrete UX patterns to adopt

1. **Containment-view as default, dependency-view on toggle** ([GitHub Next repo-vis](https://githubnext.com/projects/repo-visualization/)). Pack files-as-circles inside their package circles, root holds them all. Show import edges only on hover/selection to avoid the "hairball." This single change makes "where am I in the tree" answer itself — the user *sees* the tree before any interaction.

2. **Importance halo + pulse on the repo root and top-5 PageRank nodes** ([Linkurious Ogma halo example](https://doc.linkurious.com/ogma/latest/examples/node-halo.html)). Halo communicates "this matters" pre-attentively. Without it, even correct sizing under-emphasizes the root because radius is just one of many varying properties.

3. **Mini-map (overview panel) bottom-right with a viewport rectangle** ([Cambridge Intelligence large-network strategies](https://cambridge-intelligence.com/visualize-large-networks/)). At 40K nodes, the user gets lost on pan/zoom. Mini-map renders the full graph in 200×200px (downsampled, no labels) with a draggable rectangle for the main view. Standard pattern in Bloom, KeyLines, Gephi.

4. **Layout switcher with smooth transition, not a hard re-render** ([Cambridge Intelligence layouts for large networks](https://cambridge-intelligence.com/large-network-visualization/)). When the user toggles ELK ↔ containment ↔ FA2, interpolate positions over 600ms. Without this, every layout change feels like a context loss. Sigma supports per-node `(x,y)` animation natively.

5. **"Focus on this node" as a one-key shortcut + click affordance** ([Sourcegraph cross-repo navigation](https://sourcegraph.com/blog/cross-repository-code-navigation)). Selecting a node and pressing `f` (or double-clicking) re-centers the graph on that node with depth=2 BFS. This converts the 40K-node abstract canvas into a "give me everything near *this*" tool — which is what users actually want 90% of the time.

Optional (P2, evaluate after P1 lands):
- **Fisheye lens** on hover ([Tominski fisheye tree views, IEEE 2006, still SOTA](https://vca.informatik.uni-rostock.de/~ct/publications/Tominski06GraphLenses.pdf)). Local magnification without losing context. Powerful but easy to over-engineer; defer until users ask for it.

## References

- [PkgPulse: Cytoscape.js vs vis-network vs Sigma.js 2026](https://www.pkgpulse.com/blog/cytoscape-vs-vis-network-vs-sigma-graph-visualization-javascript-2026) — scale ceilings, layout library coverage
- [Sigma.js GitHub Discussion #1477: Hierarchical Layout](https://github.com/jacomyal/sigma.js/discussions/1477) — Dagre + d3-hierarchy + elkjs integration patterns
- [Eclipse Layout Kernel (ELK)](https://eclipse.dev/elk/) — Layered algorithm for dependency graphs
- [React Flow ELK example](https://reactflow.dev/examples/layout/elkjs) — production-grade ELK integration patterns
- [GitHub Next: Visualizing a Codebase](https://githubnext.com/projects/repo-visualization/) — circle-pack containment view, root-as-canvas
- [Neo4j Bloom 1.4 hierarchical layouts release notes](https://neo4j.com/blog/twin4j/this-week-in-neo4j-hierarchical-layouts-in-bloom-1-4-graph-data-science-with-lynxkite-fullstack-graphql-book-club/) — PageRank-driven node sizing as canonical pattern
- [Linkurious Ogma: Node Halo example](https://doc.linkurious.com/ogma/latest/examples/node-halo.html) — halo as importance affordance
- [KeyLines Graph Centrality (Cambridge Intelligence)](https://keylines.cambridge-intelligence.com/centrality.htm) — PageRank vs degree vs betweenness for emphasis
- [Cambridge Intelligence: Graph visualization at scale](https://cambridge-intelligence.com/visualize-large-networks/) — mini-map, layout-switching, hairball mitigation
- [Cambridge Intelligence: Layouts for large network visualization](https://cambridge-intelligence.com/large-network-visualization/) — organic + sequential dual-layout strategy
- [Sourcegraph: Cross-Repository Code Navigation](https://sourcegraph.com/blog/cross-repository-code-navigation) — SCIP-based progressive navigation
- [Interaction Design Foundation: Progressive Disclosure](https://ixdf.org/literature/topics/progressive-disclosure) — depth-budget UX pattern
- [Tominski et al., Fisheye Tree Views and Lenses for Graph Visualization (IEEE 2006)](https://vca.informatik.uni-rostock.de/~ct/publications/Tominski06GraphLenses.pdf) — focus+context fisheye, still SOTA
- [Code-Craft: Hierarchical Graph-Based Code Summarization (arXiv 2504.08975)](https://arxiv.org/pdf/2504.08975) — recent academic confirmation that hierarchical (not flat force) layouts dominate code-graph use cases
