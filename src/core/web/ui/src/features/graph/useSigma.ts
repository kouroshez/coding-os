import { useCallback, useEffect, useRef, useState } from 'react';
import Sigma from 'sigma';
import Graph from 'graphology';
import forceAtlas2 from 'graphology-layout-forceatlas2';
import noverlap from 'graphology-layout-noverlap';
import type { SigmaEdgeAttrs, SigmaNodeAttrs } from './graph-adapter';
import { applyDagreLayout } from './dagre-layout';
import { NodeImageProgram } from "@sigma/node-image";

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
    let inboundEdges: Set<string> | null = null;
    let outboundEdges: Set<string> | null = null;
    let currentLOD = 2; // 0 = zoomed far out, 1 = zoomed mid, 2 = zoomed in

    // Cast graph for Sigma's less-permissive generic bounds.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const sigma = new Sigma(graph as any, containerRef.current, {
      nodeProgramClasses: {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        image: NodeImageProgram as any,
      },
      renderLabels: true,
      labelSize: 12,
      labelColor: { color: labelHex },
      labelRenderedSizeThreshold: 9,
      labelDensity: 0.8,
      labelGridCellSize: 90,
      defaultNodeColor: fallbackNodeHex,
      defaultEdgeColor: edgeHex,
      defaultEdgeType: "arrow",
      minCameraRatio: 0.05,
      maxCameraRatio: 30,
      hideEdgesOnMove: false,
      nodeReducer: (node: string, data: SigmaNodeAttrs) => {
        if (data.hidden) return { ...data, hidden: true };
        
        const nodeData = { ...data };
        
        // Dynamic LOD: hide very low level concepts when zoomed out
        if (!hoveredNode) {
          if (currentLOD <= 1) {
            if (['variable', 'field', 'method', 'function', 'import_', 'identifier', 'type'].includes(data.kind || '')) {
              nodeData.hidden = true;
            }
          }
          if (currentLOD === 0) {
            if (['file', 'class', 'interface', 'task', 'doc_file', 'doc_heading', 'doc_frontmatter', 'doc_external', 'rule', 'skill', 'contract', 'community'].includes(data.kind || '')) {
              nodeData.hidden = true;
            }
          }
        }

        if (hoveredNode && hoveredNeighbours) {
          if (node === hoveredNode) {
            return { ...nodeData, size: nodeData.size * 1.4, zIndex: 2 };
          }
          if (!hoveredNeighbours.has(node)) {
            return { ...nodeData, color: '#d4ccbf', label: '', zIndex: 0 };
          }
          return { ...nodeData, zIndex: 1 };
        }
        return nodeData;
      },
      edgeReducer: (edge: string, data: SigmaEdgeAttrs) => {
        if (data.hidden) return { ...data, hidden: true };
        if (hoveredNode && inboundEdges && outboundEdges) {
          if (outboundEdges.has(edge)) {
            return { ...data, size: Math.max(data.size * 2, 2), color: '#d96c2c', zIndex: 2 }; // Outbound (orange)
          }
          if (inboundEdges.has(edge)) {
            return { ...data, size: Math.max(data.size * 2, 2), color: '#3A7A7A', zIndex: 1 }; // Inbound (teal)
          }
          return { ...data, color: '#e7dfd0', size: 0.4, zIndex: 0 };
        }
        return data;
      },
    });
    sigmaRef.current = sigma;

    sigma.on('clickNode', (e: { node: string }) => options.onNodeClick?.(e.node));
    sigma.on('clickStage', () => options.onStageClick?.());
    
    sigma.getCamera().on('updated', () => {
      const ratio = sigma.getCamera().ratio;
      let newLOD = 2; 
      if (ratio > 3.0) newLOD = 0;
      else if (ratio > 1.2) newLOD = 1;
      
      if (newLOD !== currentLOD) {
        currentLOD = newLOD;
        sigma.refresh();
      }
    });

    sigma.on('enterNode', (e: { node: string }) => {
      hoveredNode = e.node;
      const live = graphRef.current;
      if (live) {
        hoveredNeighbours = new Set([e.node]);
        inboundEdges = new Set();
        outboundEdges = new Set();

        const MAX_DEPTH = 3;

        // BFS Outbound (Dependencies)
        let outQueue = [e.node];
        let depth = 0;
        while (outQueue.length > 0 && depth < MAX_DEPTH) {
          const nextQueue: string[] = [];
          for (const n of outQueue) {
            live.outEdges(n).forEach((edge: string) => {
              outboundEdges!.add(edge);
              const target = live.target(edge);
              if (!hoveredNeighbours!.has(target)) {
                hoveredNeighbours!.add(target);
                nextQueue.push(target);
              }
            });
          }
          outQueue = nextQueue;
          depth++;
        }

        // BFS Inbound (Dependents)
        let inQueue = [e.node];
        depth = 0;
        while (inQueue.length > 0 && depth < MAX_DEPTH) {
          const nextQueue: string[] = [];
          for (const n of inQueue) {
            live.inEdges(n).forEach((edge: string) => {
              inboundEdges!.add(edge);
              const source = live.source(edge);
              if (!hoveredNeighbours!.has(source)) {
                hoveredNeighbours!.add(source);
                nextQueue.push(source);
              }
            });
          }
          inQueue = nextQueue;
          depth++;
        }
      } else {
        hoveredNeighbours = new Set([e.node]);
        inboundEdges = new Set();
        outboundEdges = new Set();
      }
      sigma.refresh();
    });
    sigma.on('leaveNode', () => {
      hoveredNode = null;
      hoveredNeighbours = null;
      inboundEdges = null;
      outboundEdges = null;
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
            settings: { ...inferred, slowDown: 5, scalingRatio: 15, gravity: 0.4, edgeWeightInfluence: 1 },
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
