// Public contract of the useSigma hook: layout mode, options, handles.

import type Graph from 'graphology';
import type { SigmaEdgeAttrs, SigmaNodeAttrs } from './graph-adapter';

export type LayoutMode = 'force' | 'dagre';

// Hook that owns a single Sigma instance bound to a container ref.
// Usage:
//   const { containerRef, setGraph } = useSigma({ onNodeClick: setSelected });
//   useEffect(() => setGraph(buildGraph(payload)), [payload]);
//
// Layout: ForceAtlas2 runs in a Web Worker (FA2LayoutSupervisor) so the
// main thread stays free for user interaction (click, pan, zoom) while
// the layout converges. Wall-clock bounded so we always finish in
// O(seconds). Noverlap is a fast sync polish pass after the worker stops.

export interface UseSigmaOptions {
  onNodeClick?: (uid: string) => void;
  onStageClick?: () => void;
}

export interface UseSigmaReturn {
  containerRef: React.RefObject<HTMLDivElement | null>;
  setGraph: (
    graph: Graph<SigmaNodeAttrs, SigmaEdgeAttrs>,
    options?: { layout?: LayoutMode },
  ) => void;
  isLayoutRunning: boolean;
}

// Wall-clock budget for the FA2 worker. Scales with node count so a
// small graph converges fast and a big one gets enough cycles, but
// never blocks the user past ~3 s of waiting for "layout settled".
// The worker runs off main thread so this never freezes the UI —
// the budget caps how long the layout keeps adjusting, not how long
// the user has to wait to interact.
