import { useCallback, useEffect, useRef, useState } from 'react';
import Sigma from 'sigma';
import Graph from 'graphology';
import forceAtlas2 from 'graphology-layout-forceatlas2';
import noverlap from 'graphology-layout-noverlap';
import type { SigmaEdgeAttrs, SigmaNodeAttrs } from './graph-adapter';
import { applyDagreLayout } from './dagre-layout';

export type LayoutMode = 'force' | 'dagre';

// Hook that owns a single Sigma instance bound to a container ref.
// Usage:
//   const { containerRef, setGraph } = useSigma({ onNodeClick: setSelected });
//   useEffect(() => setGraph(buildGraph(payload)), [payload]);
//
// Layout: synchronous ForceAtlas2 for up to 200 iterations, then a
// light noverlap pass. Worker-based layout is a V2 optimization per
// slice spec.

interface UseSigmaOptions {
  onNodeClick?: (uid: string) => void;
  onStageClick?: () => void;
}

interface UseSigmaReturn {
  containerRef: React.RefObject<HTMLDivElement>;
  setGraph: (
    graph: Graph<SigmaNodeAttrs, SigmaEdgeAttrs>,
    options?: { layout?: LayoutMode },
  ) => void;
  isLayoutRunning: boolean;
}

const FA2_ITERATIONS = 200;
const NOVERLAP_SETTINGS = {
  maxIterations: 30,
  ratio: 1.1,
  margin: 6,
  expansion: 1.05,
};

export function useSigma(options: UseSigmaOptions = {}): UseSigmaReturn {
  const containerRef = useRef<HTMLDivElement>(null);
  // Sigma's generics are strict about assignability; keep the stored ref
  // loose and rely on our wrapper functions to enforce attr shapes.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const sigmaRef = useRef<any>(null);
  const graphRef = useRef<Graph<SigmaNodeAttrs, SigmaEdgeAttrs> | null>(null);
  const [isLayoutRunning, setLayoutRunning] = useState(false);

  useEffect(() => {
    if (!containerRef.current) return;

    const graph = new Graph<SigmaNodeAttrs, SigmaEdgeAttrs>({ multi: true });
    graphRef.current = graph;

    // Read brand tokens at mount so labels and edges follow the active
    // theme. Falls back to safe neutrals if the variables are missing.
    const cs = getComputedStyle(containerRef.current);
    const labelHex = cs.getPropertyValue('--cos-text').trim() || '#1a1814';
    const edgeHex = cs.getPropertyValue('--cos-border').trim() || '#b8ad9a';
    const fallbackNodeHex = cs.getPropertyValue('--cos-muted').trim() || '#6b665e';

    // Hover-highlight state. Closed over by the reducers below; mutated
    // by the enterNode / leaveNode listeners. Keeping it here (not in
    // useState) so a hover doesn't trigger a React re-render — sigma
    // handles the repaint itself via .refresh().
    let hoveredNode: string | null = null;
    let hoveredNeighbours: Set<string> | null = null;
    const hostGraph = graph;

    // Cast graph for Sigma's less-permissive generic bounds.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const sigma = new Sigma(graph as any, containerRef.current, {
      renderLabels: true,
      labelSize: 12,
      labelColor: { color: labelHex },
      labelRenderedSizeThreshold: 9,
      labelDensity: 0.8,
      labelGridCellSize: 90,
      defaultNodeColor: fallbackNodeHex,
      defaultEdgeColor: edgeHex,
      minCameraRatio: 0.05,
      maxCameraRatio: 30,
      hideEdgesOnMove: false,
      nodeReducer: (node: string, data: SigmaNodeAttrs) => {
        if (data.hidden) return { ...data, hidden: true };
        if (hoveredNode && hoveredNeighbours) {
          if (node === hoveredNode) {
            return { ...data, size: data.size * 1.4, zIndex: 2 };
          }
          if (!hoveredNeighbours.has(node)) {
            return { ...data, color: '#d4ccbf', label: '', zIndex: 0 };
          }
          return { ...data, zIndex: 1 };
        }
        return data;
      },
      edgeReducer: (edge: string, data: SigmaEdgeAttrs) => {
        if (data.hidden) return { ...data, hidden: true };
        if (hoveredNode) {
          if (hostGraph.hasExtremity(edge, hoveredNode)) {
            return { ...data, size: data.size * 2, color: '#3A2925' };
          }
          return { ...data, color: '#e7dfd0', size: 0.4 };
        }
        return data;
      },
    });
    sigmaRef.current = sigma;

    sigma.on('clickNode', (e: { node: string }) => options.onNodeClick?.(e.node));
    sigma.on('clickStage', () => options.onStageClick?.());
    sigma.on('enterNode', (e: { node: string }) => {
      hoveredNode = e.node;
      const live = graphRef.current;
      hoveredNeighbours = live
        ? new Set([e.node, ...live.neighbors(e.node)])
        : new Set([e.node]);
      sigma.refresh();
    });
    sigma.on('leaveNode', () => {
      hoveredNode = null;
      hoveredNeighbours = null;
      sigma.refresh();
    });

    return () => {
      sigma.kill();
      sigmaRef.current = null;
      graphRef.current = null;
    };
    // Intentionally run once; callbacks read from the latest options via closure identity
    // (options is used as a ref via the outer scope; re-mount is driven by `setGraph`).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setGraph = useCallback(
    (
      incoming: Graph<SigmaNodeAttrs, SigmaEdgeAttrs>,
      options: { layout?: LayoutMode } = {},
    ) => {
      const sigma = sigmaRef.current;
      if (!sigma) return;

      if (incoming.order === 0) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        sigma.setGraph(incoming as any);
        graphRef.current = incoming;
        return;
      }

      setLayoutRunning(true);
      const layout: LayoutMode = options.layout ?? 'force';
      if (layout === 'dagre') {
        // TASK-141 P5: top-down hierarchical layout for the
        // Containment view. Skip force-atlas + noverlap so we don't
        // wrestle the carefully ranked tree back into a hairball.
        applyDagreLayout(incoming);
      } else {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const inferred = forceAtlas2.inferSettings(incoming as any);
        forceAtlas2.assign(
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          incoming as any,
          {
            iterations: FA2_ITERATIONS,
            settings: { ...inferred, slowDown: 5, scalingRatio: 15, gravity: 0.4 },
          },
        );
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        noverlap.assign(incoming as any, NOVERLAP_SETTINGS);
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      sigma.setGraph(incoming as any);
      graphRef.current = incoming;
      sigma.getCamera().animatedReset({ duration: 400 });
      setLayoutRunning(false);
    },
    [],
  );

  return { containerRef, setGraph, isLayoutRunning };
}
