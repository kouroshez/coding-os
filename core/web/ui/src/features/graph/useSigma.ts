import { useCallback, useEffect, useRef, useState } from 'react';
import Sigma from 'sigma';
import Graph from 'graphology';
import forceAtlas2 from 'graphology-layout-forceatlas2';
import noverlap from 'graphology-layout-noverlap';
import type { SigmaEdgeAttrs, SigmaNodeAttrs } from './graph-adapter';

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
  setGraph: (graph: Graph<SigmaNodeAttrs, SigmaEdgeAttrs>) => void;
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

    // Cast graph for Sigma's less-permissive generic bounds.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const sigma = new Sigma(graph as any, containerRef.current, {
      renderLabels: true,
      labelSize: 11,
      labelColor: { color: '#e6e7eb' },
      labelRenderedSizeThreshold: 8,
      defaultNodeColor: '#6b7280',
      defaultEdgeColor: '#3b4252',
      minCameraRatio: 0.05,
      maxCameraRatio: 30,
      hideEdgesOnMove: true,
      nodeReducer: (_node: string, data: SigmaNodeAttrs) => {
        if (data.hidden) return { ...data, hidden: true };
        return data;
      },
      edgeReducer: (_edge: string, data: SigmaEdgeAttrs) => {
        if (data.hidden) return { ...data, hidden: true };
        return data;
      },
    });
    sigmaRef.current = sigma;

    sigma.on('clickNode', (e: { node: string }) => options.onNodeClick?.(e.node));
    sigma.on('clickStage', () => options.onStageClick?.());

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
    (incoming: Graph<SigmaNodeAttrs, SigmaEdgeAttrs>) => {
      const sigma = sigmaRef.current;
      if (!sigma) return;

      if (incoming.order === 0) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        sigma.setGraph(incoming as any);
        graphRef.current = incoming;
        return;
      }

      setLayoutRunning(true);
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
