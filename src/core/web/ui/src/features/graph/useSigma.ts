import { useCallback, useEffect, useRef, useState } from 'react';
import Sigma from 'sigma';
import Graph from 'graphology';
import forceAtlas2 from 'graphology-layout-forceatlas2';
import FA2LayoutSupervisor from 'graphology-layout-forceatlas2/worker';
import noverlap from 'graphology-layout-noverlap';
import type { SigmaEdgeAttrs, SigmaNodeAttrs } from './graph-adapter';
import { applyDagreLayout } from './dagre-layout';
import { NodeImageProgram } from "@sigma/node-image";
import { useGraphStore } from '@/store/graph-store';
import { useThemeStore } from '@/store/theme-store';
import { kindColor, isRootUid, ROOT_COLOR } from '@/lib/node-colors';

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

interface UseSigmaOptions {
  onNodeClick?: (uid: string) => void;
  onStageClick?: () => void;
}

interface UseSigmaReturn {
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
const FA2_BUDGET_MIN_MS = 800;
const FA2_BUDGET_MAX_MS = 3000;
const FA2_BUDGET_PER_NODE_MS = 1.2; // measured empirically on Barnes-Hut

const NOVERLAP_SETTINGS = {
  maxIterations: 30,
  ratio: 1.1,
  // TASK-406: wider margins give the layout more base spacing so the
  // zoom-adaptive sizing has room to breathe at overview ratios.
  margin: 10,
  expansion: 1.08,
};

function _fa2Budget(nodeCount: number): number {
  return Math.max(
    FA2_BUDGET_MIN_MS,
    Math.min(FA2_BUDGET_MAX_MS, Math.round(nodeCount * FA2_BUDGET_PER_NODE_MS)),
  );
}

export function useSigma(options: UseSigmaOptions = {}): UseSigmaReturn {
  const containerRef = useRef<HTMLDivElement>(null);
  // Sigma's generics are strict about assignability; keep the stored ref
  // loose and rely on our wrapper functions to enforce attr shapes.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const sigmaRef = useRef<any>(null);
  const graphRef = useRef<Graph<SigmaNodeAttrs, SigmaEdgeAttrs> | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const supervisorRef = useRef<any>(null);
  const layoutTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [isLayoutRunning, setLayoutRunning] = useState(false);
  const updateSearchRef = useRef<((query: string) => void) | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const graph = new Graph<SigmaNodeAttrs, SigmaEdgeAttrs>({ multi: true });
    graphRef.current = graph;

    // Read brand tokens at mount so labels and edges follow the active
    // theme. Falls back to safe neutrals if the variables are missing.
    const cs = getComputedStyle(containerRef.current);
    const labelHex = cs.getPropertyValue('--cos-text').trim() || '#e7eaf0';
    const edgeHex = cs.getPropertyValue('--cos-border').trim() || '#2c313a';
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

    // Search query sets for high-fidelity path highlighting
    const matchedNodes = new Set<string>();
    const matchedPaths = new Set<string>();
    const matchedEdges = new Set<string>();

    const updateSearchHighlight = (query: string) => {
      matchedNodes.clear();
      matchedPaths.clear();
      matchedEdges.clear();

      const q = query.trim().toLowerCase();
      if (!q) return;

      const live = graphRef.current;
      if (!live) return;

      // 1. Find all directly matched nodes (case-insensitive on label or uid)
      live.forEachNode((node: string, data: SigmaNodeAttrs) => {
        const label = (data.label || '').toLowerCase();
        const uid = node.toLowerCase();
        if (label.includes(q) || uid.includes(q)) {
          matchedNodes.add(node);
          matchedPaths.add(node);
        }
      });

      // 2. BFS from matched nodes to depth 1 (immediate adjacent paths)
      const MAX_SEARCH_DEPTH = 1;
      let currentQueue = Array.from(matchedNodes);
      
      for (let depth = 0; depth < MAX_SEARCH_DEPTH; depth++) {
        const nextQueue: string[] = [];
        for (const n of currentQueue) {
          // Outbound (target nodes and edges)
          live.outEdges(n).forEach((edge: string) => {
            const target = live.target(edge);
            matchedEdges.add(edge);
            if (!matchedPaths.has(target)) {
              matchedPaths.add(target);
              nextQueue.push(target);
            }
          });
          // Inbound (source nodes and edges)
          live.inEdges(n).forEach((edge: string) => {
            const source = live.source(edge);
            matchedEdges.add(edge);
            if (!matchedPaths.has(source)) {
              matchedPaths.add(source);
              nextQueue.push(source);
            }
          });
        }
        currentQueue = nextQueue;
      }
    };

    updateSearchRef.current = updateSearchHighlight;

    // Cast graph for Sigma's less-permissive generic bounds.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const sigma = new Sigma(graph as any, containerRef.current, {
      nodeProgramClasses: {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        image: NodeImageProgram as any,
      },
      // Tolerate a zero-width host at mount — the Cognition page (and any
      // tab that mounts the canvas inside a not-yet-laid-out flex column)
      // would otherwise throw "Sigma: Container has no width" on first
      // paint (TASK-409); Sigma re-measures on the next resize/refresh.
      allowInvalidContainer: true,
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
        const query = useGraphStore.getState().searchQuery.trim().toLowerCase();
        
        // Dynamic LOD: hide very low level concepts when zoomed out
        // Disable LOD rules when active search query exists so matching elements are not hidden
        if (!hoveredNode && !query) {
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

        // Hover highlight state takes precedence
        if (hoveredNode && hoveredNeighbours) {
          if (node === hoveredNode) {
            return { ...nodeData, size: nodeData.size * 1.4, zIndex: 10 };
          }
          if (!hoveredNeighbours.has(node)) {
            return { ...nodeData, color: '#33415530', label: '', zIndex: 0 };
          }
          return { ...nodeData, zIndex: 5 };
        }

        // Search highlight path state
        if (query) {
          if (matchedNodes.has(node)) {
            return { ...nodeData, size: nodeData.size * 1.5, zIndex: 10 };
          }
          if (matchedPaths.has(node)) {
            return { ...nodeData, zIndex: 5 };
          }
          return { ...nodeData, color: '#33415520', label: '', zIndex: 0 };
        }

        return nodeData;
      },
      edgeReducer: (edge: string, data: SigmaEdgeAttrs) => {
        if (data.hidden) return { ...data, hidden: true };

        // Hover highlight state takes precedence
        if (hoveredNode && inboundEdges && outboundEdges) {
          if (outboundEdges.has(edge)) {
            return { ...data, size: Math.max(data.size * 2, 2), color: '#7c82f2', zIndex: 10 }; // Outbound (Iris)
          }
          if (inboundEdges.has(edge)) {
            return { ...data, size: Math.max(data.size * 2, 2), color: '#3b82f6', zIndex: 5 }; // Inbound (blue)
          }
          return { ...data, color: '#33415510', size: 0.4, zIndex: 0 };
        }

        // Search highlight state
        const query = useGraphStore.getState().searchQuery.trim().toLowerCase();
        if (query) {
          if (matchedEdges.has(edge)) {
            return { ...data, size: Math.max(data.size * 2.5, 2.5), color: '#7c82f2', zIndex: 5 };
          }
          return { ...data, color: '#33415505', size: 0.1, zIndex: 0 };
        }

        return data;
      },
    });
    sigmaRef.current = sigma;

    sigma.on('clickNode', (e: { node: string }) => {
      // R4-N5: community: uids are synthetic Louvain ids — not registered
      // as graph_nodes. Skip click handler so NodeInspector doesn't fire
      // /api/graph/context/community:* which the backend rejects with
      // the canonical UID-scheme error. Hover-highlighting still works.
      if (e.node.startsWith('community:')) return;
      options.onNodeClick?.(e.node);
    });
    sigma.on('clickStage', () => options.onStageClick?.());
    
    sigma.getCamera().on('updated', () => {
      const ratio = sigma.getCamera().ratio;
      let newLOD = 2;
      if (ratio > 3.0) newLOD = 0;
      else if (ratio > 1.2) newLOD = 1;

      if (newLOD !== currentLOD) {
        currentLOD = newLOD;
        // TASK-406: adaptive sizing — past the mid-zoom threshold node
        // sizes follow GRAPH positions (linear ratio) instead of staying
        // fixed-pixel, so zoomed-out circles shrink with the layout and
        // stop piling on top of each other (Sigma's documented remedy;
        // Cambridge Intelligence "adapt styles per zoom level"). Zoomed
        // in, restore the default sqrt curve for readable labels.
        sigma.setSetting(
          'zoomToSizeRatioFunction',
          newLOD <= 1 ? (r: number) => r : (r: number) => Math.sqrt(r),
        );
        sigma.setSetting('labelRenderedSizeThreshold', newLOD === 0 ? 24 : 9);
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

    // Initial search computation if search query exists
    const initialQuery = useGraphStore.getState().searchQuery;
    if (initialQuery) {
      updateSearchHighlight(initialQuery);
    }

    // Subscribe to graph-store searchQuery changes
    let prevSearchQuery = useGraphStore.getState().searchQuery;
    const unsubscribe = useGraphStore.subscribe((state) => {
      if (state.searchQuery !== prevSearchQuery) {
        prevSearchQuery = state.searchQuery;
        updateSearchHighlight(state.searchQuery);
        sigma.refresh();
      }
    });

    return () => {
      unsubscribe();
      // Tear down the worker FIRST so it doesn't try to mutate a
      // graph whose Sigma render has already been killed.
      if (layoutTimerRef.current) {
        clearTimeout(layoutTimerRef.current);
        layoutTimerRef.current = null;
      }
      if (supervisorRef.current) {
        try {
          supervisorRef.current.stop();
          supervisorRef.current.kill();
        } catch {
          // supervisor may already be dead; ignore
        }
        supervisorRef.current = null;
      }
      sigma.kill();
      sigmaRef.current = null;
      graphRef.current = null;
    };
    // Intentionally run once; callbacks read from the latest options via closure identity
    // (options is used as a ref via the outer scope; re-mount is driven by `setGraph`).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Recolor nodes in place when the global theme toggles — positions are
  // preserved (no rebuild, no layout re-run). Node colors are baked at
  // build time (graph-adapter), so on a light↔dark switch we repaint each
  // node from the theme's palette and refresh the label color token.
  useEffect(() => {
    return useThemeStore.subscribe((s) => {
      const live = graphRef.current;
      const sig = sigmaRef.current;
      if (!live || !sig || !containerRef.current) return;
      live.forEachNode((n: string, d: SigmaNodeAttrs) => {
        // Root anchor keeps its reserved focal color across a theme
        // toggle — it is NOT a categorical folder (TASK-408).
        live.setNodeAttribute(n, 'color', isRootUid(n) ? ROOT_COLOR : kindColor(d.kind, s.theme));
      });
      const cs = getComputedStyle(containerRef.current);
      sig.setSetting('labelColor', {
        color: cs.getPropertyValue('--cos-text').trim() || '#e7eaf0',
      });
      sig.refresh();
    });
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
        updateSearchRef.current?.(useGraphStore.getState().searchQuery);
        return;
      }

      // Kill any prior worker — a fresh setGraph means the previous
      // layout result is now obsolete. Without this the supervisor
      // would keep writing positions into a graph instance Sigma
      // has already swapped out.
      if (layoutTimerRef.current) {
        clearTimeout(layoutTimerRef.current);
        layoutTimerRef.current = null;
      }
      if (supervisorRef.current) {
        try {
          supervisorRef.current.stop();
          supervisorRef.current.kill();
        } catch {
          // supervisor may already be dead; ignore
        }
        supervisorRef.current = null;
      }

      setLayoutRunning(true);
      const layout: LayoutMode = options.layout ?? 'force';

      if (layout === 'dagre') {
        // top-down hierarchical layout for the
        // Containment view. Skip force-atlas so we don't wrestle the
        // carefully ranked tree back into a hairball.
        applyDagreLayout(incoming);
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        sigma.setGraph(incoming as any);
        graphRef.current = incoming;
        updateSearchRef.current?.(useGraphStore.getState().searchQuery);
        sigma.getCamera().animatedReset({ duration: 400 });
        setLayoutRunning(false);
        return;
      }

      // Force layout: hand off to the worker. We attach the graph to
      // Sigma immediately so the user sees nodes (in initial positions)
      // while the worker iterates; subsequent worker writes update
      // positions in place and Sigma re-renders each frame.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const inferred = forceAtlas2.inferSettings(incoming as any);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      sigma.setGraph(incoming as any);
      graphRef.current = incoming;
      updateSearchRef.current?.(useGraphStore.getState().searchQuery);
      sigma.getCamera().animatedReset({ duration: 400 });

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const supervisor = new FA2LayoutSupervisor(incoming as any, {
        settings: {
          ...inferred,
          barnesHutOptimize: true,
          barnesHutTheta: 0.5,
          slowDown: 5,
          scalingRatio: 15,
          gravity: 0.4,
          edgeWeightInfluence: 1,
        },
      });
      supervisorRef.current = supervisor;
      supervisor.start();

      const budgetMs = _fa2Budget(incoming.order);
      layoutTimerRef.current = setTimeout(() => {
        try {
          supervisor.stop();
          // Fast sync polish so labels don't overlap once the worker
          // has done the heavy spatialising. Noverlap is O(n) per
          // iteration with maxIterations=30 — sub-100ms even on 5K
          // nodes, so running it on the main thread is fine.
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          noverlap.assign(incoming as any, NOVERLAP_SETTINGS);
          supervisor.kill();
        } catch {
          // supervisor may already be dead; ignore
        }
        if (supervisorRef.current === supervisor) supervisorRef.current = null;
        layoutTimerRef.current = null;
        setLayoutRunning(false);
        sigma.refresh();
      }, budgetMs);
    },
    [],
  );

  return { containerRef, setGraph, isLayoutRunning };
}
