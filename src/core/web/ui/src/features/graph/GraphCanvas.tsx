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
  const overviewBudgetByDepth: Record<string, number> = {
    '1': 120,
    '2': 320,
    '3': 700,
    all: 1400,
  };
  const rootedBudgetByDepth: Record<string, number> = {
    '1': 80,
    '2': 250,
    '3': 600,
    all: 1500,
  };
  const depthKey = String(depth);
  const exportParams: Record<string, unknown> = {
    format: 'json',
    max_nodes: selectedRootUid
      ? rootedBudgetByDepth[depthKey] ?? 600
      : overviewBudgetByDepth[depthKey] ?? 400,
    mode: viewMode,
  };
  if (selectedRootUid) {
    exportParams.root_uid = selectedRootUid;
    exportParams.include_spine = true;
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
          className="absolute left-3 top-3 rounded bg-rose-900/80 px-2 py-1 text-xs"
        >
          {error.message}
        </div>
      )}
      {!isLoading && !error && pruned && pruned.nodes?.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-[var(--cos-muted)]">
          no nodes reachable at this depth
        </div>
      )}
    </div>
  );
}
