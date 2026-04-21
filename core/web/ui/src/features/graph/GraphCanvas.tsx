import { useEffect, useMemo } from 'react';
import { useGraphStore } from '@/store/graph-store';
import { useApiGet } from '@/lib/hooks';
import { useSigma } from './useSigma';
import { buildGraph, bfsSubgraph, type ApiGraphPayload } from './graph-adapter';

// Sigma host. Three-state UI:
//  - selectedRootUid === null → CTA placeholder (anti-hairball #1)
//  - query pending           → loading overlay
//  - query error             → error banner
//  - query empty              → empty message
//  - otherwise                → WebGL canvas via Sigma.js
export default function GraphCanvas() {
  const selectedRootUid = useGraphStore((s) => s.selectedRootUid);
  const depth = useGraphStore((s) => s.depth);
  const visibleKinds = useGraphStore((s) => s.visibleKinds);
  const visibleEdgeTypes = useGraphStore((s) => s.visibleEdgeTypes);
  const setSelectedNode = useGraphStore((s) => s.setSelectedNode);

  const { containerRef, setGraph, isLayoutRunning } = useSigma({
    onNodeClick: (uid) => setSelectedNode(uid),
    onStageClick: () => setSelectedNode(null),
  });

  const enabled = Boolean(selectedRootUid);
  const { data, isLoading, error } = useApiGet<ApiGraphPayload>(
    ['graph-export', selectedRootUid ?? ''],
    '/api/graph/export',
    {
      format: 'json',
      root_uid: selectedRootUid ?? '',
      max_nodes: 500,
      include_spine: true,
    },
    { enabled },
  );

  const pruned = useMemo<ApiGraphPayload | null>(() => {
    if (!data || !selectedRootUid) return null;
    const maxDepth = depth === 'all' ? null : depth;
    return bfsSubgraph(data, selectedRootUid, maxDepth);
  }, [data, selectedRootUid, depth]);

  useEffect(() => {
    if (!pruned) return;
    const graph = buildGraph(pruned, {
      visibleKinds: new Set(visibleKinds),
      visibleEdgeTypes: new Set(visibleEdgeTypes),
    });
    setGraph(graph);
  }, [pruned, visibleKinds, visibleEdgeTypes, setGraph]);

  if (!selectedRootUid) {
    return (
      <div className="flex h-full items-center justify-center text-center">
        <div className="max-w-md px-6">
          <h2 className="mb-2 text-lg font-semibold">Pick a node to explore</h2>
          <p className="text-sm text-[#9ea4ae]">
            The canvas stays empty until you pick a root. Use the CONTAINS tree on the
            left to jump to any folder, file, class, or method — depth-bounded BFS
            keeps the view readable.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="absolute inset-0" aria-label="graph canvas" />
      {isLoading && (
        <div
          role="status"
          className="absolute left-3 top-3 rounded bg-[#151a22] px-2 py-1 text-xs"
        >
          loading…
        </div>
      )}
      {isLayoutRunning && !isLoading && (
        <div
          role="status"
          className="absolute left-3 top-3 rounded bg-[#151a22] px-2 py-1 text-xs"
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
        <div className="absolute inset-0 flex items-center justify-center text-sm text-[#9ea4ae]">
          no nodes reachable at this depth
        </div>
      )}
    </div>
  );
}
