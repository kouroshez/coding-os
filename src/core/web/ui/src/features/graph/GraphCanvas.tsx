import { useEffect, useMemo } from 'react';
import { useGraphStore } from '@/store/graph-store';
import { useApiGet } from '@/lib/hooks';
import { useSigma } from './useSigma';
import { buildGraph, bfsSubgraph, type ApiGraphPayload } from './graph-adapter';

// Sigma host. Renders the smart-blend overview by default (TASK-141 P1)
// or a depth-bounded BFS subgraph when a root is pinned.  Noise nodes
// (frontmatter / heading-only) are hidden by both server-side noise
// filter (TASK-141 P1) and the client-side `visibleKinds` toggles.
export default function GraphCanvas() {
  const selectedRootUid = useGraphStore((s) => s.selectedRootUid);
  const viewMode = useGraphStore((s) => s.viewMode);
  const depth = useGraphStore((s) => s.depth);
  const visibleKinds = useGraphStore((s) => s.visibleKinds);
  const visibleEdgeTypes = useGraphStore((s) => s.visibleEdgeTypes);
  const setSelectedNode = useGraphStore((s) => s.setSelectedNode);

  const { containerRef, setGraph, isLayoutRunning } = useSigma({
    onNodeClick: (uid) => setSelectedNode(uid),
    onStageClick: () => setSelectedNode(null),
  });

  // Build params explicitly so we never send `root_uid=""` (empty
  // string) — the backend would interpret that as "look up empty uid,
  // find nothing" and return 0 nodes.  Pass the key only when a root
  // is actually pinned.
  // Depth-budget = max_nodes the backend returns. Sigma.js WebGL renders
  // ~40k nodes comfortably; on a 41k-node repo "all" should approach the
  // full graph for the overview view, and be permissive for rooted BFS
  // walks. Old caps were 1.4k/1.5k → ≤3.5% coverage which is what the
  // user reported as "max doesn't show 100%". Bumped 10-15× per the
  // enterprise viz audit (docs/_meta/audits/audit-graph-viz-research.md).
  const overviewBudgetByDepth: Record<string, number> = {
    '1': 200,
    '2': 800,
    '3': 3000,
    all: 20000,
  };
  const rootedBudgetByDepth: Record<string, number> = {
    '1': 150,
    '2': 600,
    '3': 1800,
    all: 10000,
  };
  const depthKey = String(depth);
  const requestedMax = selectedRootUid
    ? rootedBudgetByDepth[depthKey] ?? 600
    : overviewBudgetByDepth[depthKey] ?? 400;
  // Backend BFS used to be capped at 3 hops regardless of the slider —
  // "depth=all" returned 3-hop walks, so a folder's grandchildren were
  // visible but their contents weren't. Mirror the slider on the wire
  // so the server walks as far as the user asked.
  const rootedHopsByDepth: Record<string, number> = {
    '1': 1,
    '2': 2,
    '3': 3,
    all: 12,
  };
  const exportParams: Record<string, unknown> = {
    format: 'json',
    max_nodes: requestedMax,
    mode: viewMode,
  };
  if (selectedRootUid) {
    exportParams.root_uid = selectedRootUid;
    exportParams.include_spine = true;
    exportParams.max_hops = rootedHopsByDepth[depthKey] ?? 3;
  }
  const { data, isLoading, error } = useApiGet<ApiGraphPayload>(
    ['graph-export', selectedRootUid ?? '__overview__', viewMode, depthKey],
    '/api/graph/export',
    exportParams,
  );

  const pruned = useMemo<ApiGraphPayload | null>(() => {
    if (!data) return null;
    if (!selectedRootUid) return data;
    const maxDepth = depth === 'all' ? null : depth;
    return bfsSubgraph(data, selectedRootUid, maxDepth);
  }, [data, selectedRootUid, depth]);

  useEffect(() => {
    if (!pruned) return;
    const graph = buildGraph(pruned, {
      visibleKinds: new Set(visibleKinds),
      visibleEdgeTypes: new Set(visibleEdgeTypes),
    });
    // TASK-141 P5: containment view → top-down dagre tree; everything
    // else stays on ForceAtlas2 with noverlap.
    const layout = viewMode === 'containment' ? 'dagre' : 'force';
    setGraph(graph, { layout });
  }, [pruned, visibleKinds, visibleEdgeTypes, viewMode, setGraph]);

  // Always mount the container so Sigma can attach on first paint;
  // overlay the CTA when no root is selected.  Conditionally rendering
  // the container caused Sigma to miss the host on initial mount and
  // the canvas to never appear after a click.
  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="absolute inset-0" aria-label="graph canvas" />
      {isLoading && (
        <div
          role="status"
          className="absolute left-3 top-3 rounded bg-[var(--cos-panel)] px-2 py-1 text-xs"
        >
          loading…
        </div>
      )}
      {isLayoutRunning && !isLoading && (
        <div
          role="status"
          className="absolute left-3 top-3 rounded bg-[var(--cos-panel)] px-2 py-1 text-xs"
        >
          laying out…
        </div>
      )}
      {error && (
        <div
          role="alert"
          className="absolute left-3 top-3 rounded bg-[var(--cos-err-tint)] px-2 py-1 text-xs"
        >
          {error.message}
        </div>
      )}
      {!isLoading && !error && pruned && pruned.nodes?.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-[var(--cos-muted)]">
          no nodes reachable at this depth
        </div>
      )}
      {/* TASK-023: honest truncation badge (cert Domain 5.6 — provenance) */}
      {!isLoading && !error && pruned && (pruned.nodes?.length ?? 0) > 0 && (
        <div
          role="status"
          aria-label="node count and budget"
          className="absolute bottom-3 right-3 rounded bg-[var(--cos-panel)]/85 px-2 py-1 text-[10px] font-mono text-[var(--cos-muted)]"
        >
          {(() => {
            const shown = pruned.nodes?.length ?? 0;
            const fetched = data?.nodes?.length ?? shown;
            const truncated = fetched >= requestedMax;
            return (
              <>
                <span className="text-[var(--cos-text)]">{shown}</span>
                <span> / </span>
                <span>{fetched}</span>
                <span> nodes</span>
                {truncated && (
                  <span className="ml-1 rounded bg-[var(--cos-warn-tint)] px-1 text-[var(--cos-warn)]">
                    truncated · raise depth budget
                  </span>
                )}
              </>
            );
          })()}
        </div>
      )}
    </div>
  );
}
