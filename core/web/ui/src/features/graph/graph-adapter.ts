import Graph from 'graphology';
import { kindColor } from '@/lib/node-colors';

// Payload shape returned by /api/graph/export (S4 wrapper around
// cos_graph_export). Keeping it loose — the backend is authoritative.
export interface ApiNode {
  uid: string;
  kind: string;
  label?: string | null;
  file_path?: string | null;
  start_line?: number | null;
  end_line?: number | null;
}

export interface ApiEdge {
  source: string;
  target: string;
  edge_type: string;
  confidence?: number;
}

export interface ApiGraphPayload {
  format?: string;
  nodes?: ApiNode[];
  edges?: ApiEdge[];
}

export interface SigmaNodeAttrs {
  x: number;
  y: number;
  size: number;
  color: string;
  label: string;
  kind: string;
  filePath?: string;
  startLine?: number;
  hidden?: boolean;
}

export interface SigmaEdgeAttrs {
  size: number;
  color: string;
  edgeType: string;
  hidden?: boolean;
}

// Convert a raw export payload into a graphology Graph suitable for
// Sigma.js. Initial coordinates are random in [-1, 1] — ForceAtlas2
// will settle them on mount.
export function buildGraph(
  payload: ApiGraphPayload,
  opts: { visibleKinds?: Set<string>; visibleEdgeTypes?: Set<string> } = {},
): Graph<SigmaNodeAttrs, SigmaEdgeAttrs> {
  const graph = new Graph<SigmaNodeAttrs, SigmaEdgeAttrs>({ multi: true });

  const nodes = payload.nodes ?? [];
  const edges = payload.edges ?? [];

  for (const n of nodes) {
    if (!n.uid) continue;
    const kindVisible = opts.visibleKinds ? opts.visibleKinds.has(n.kind) : true;
    if (graph.hasNode(n.uid)) continue;
    graph.addNode(n.uid, {
      x: Math.random() * 2 - 1,
      y: Math.random() * 2 - 1,
      size: n.kind === 'folder' || n.kind === 'file' ? 6 : 4,
      color: kindColor(n.kind),
      label: n.label || n.uid,
      kind: n.kind,
      filePath: n.file_path ?? undefined,
      startLine: n.start_line ?? undefined,
      hidden: !kindVisible,
    });
  }

  for (const e of edges) {
    if (!graph.hasNode(e.source) || !graph.hasNode(e.target)) continue;
    const typeVisible = opts.visibleEdgeTypes
      ? opts.visibleEdgeTypes.has(e.edge_type)
      : true;
    const key = `${e.source}->${e.target}:${e.edge_type}`;
    if (graph.hasEdge(key)) continue;
    try {
      graph.addEdgeWithKey(key, e.source, e.target, {
        size: 1,
        color: '#3b4252',
        edgeType: e.edge_type,
        hidden: !typeVisible,
      });
    } catch {
      // duplicate — ignore
    }
  }

  return graph;
}

// Depth-bounded BFS from a root uid. Used client-side to prune the
// payload before handing it to Sigma (anti-hairball #2). The server
// already caps max_nodes; this additionally enforces a hop budget.
export function bfsSubgraph(
  payload: ApiGraphPayload,
  rootUid: string,
  maxDepth: number | null,
): ApiGraphPayload {
  if (!rootUid || !payload.nodes?.length) {
    return { nodes: [], edges: [] };
  }
  const adjacency = new Map<string, Set<string>>();
  for (const e of payload.edges ?? []) {
    if (!adjacency.has(e.source)) adjacency.set(e.source, new Set());
    if (!adjacency.has(e.target)) adjacency.set(e.target, new Set());
    adjacency.get(e.source)!.add(e.target);
    adjacency.get(e.target)!.add(e.source);
  }
  const visited = new Set<string>();
  const queue: Array<[string, number]> = [[rootUid, 0]];
  while (queue.length) {
    const [uid, depth] = queue.shift()!;
    if (visited.has(uid)) continue;
    visited.add(uid);
    if (maxDepth !== null && depth >= maxDepth) continue;
    const neighbours = adjacency.get(uid);
    if (!neighbours) continue;
    for (const n of neighbours) {
      if (!visited.has(n)) queue.push([n, depth + 1]);
    }
  }
  const nodes = (payload.nodes ?? []).filter((n) => visited.has(n.uid));
  const edges = (payload.edges ?? []).filter(
    (e) => visited.has(e.source) && visited.has(e.target),
  );
  return { nodes, edges };
}
