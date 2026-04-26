import Graph from 'graphology';
import { kindColor, normalizeKind } from '@/lib/node-colors';

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
  // Field names mirror the canonical GraphEdge type at
  // core/graph_os/types.py — verified against the live
  // /api/graph/export response per core/rules/api-contract-discipline.md.
  source_uid: string;
  target_uid: string;
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

// TASK-141 P4: client-side noise filter — keeps the canvas focused on
// real navigation targets even when the backend returns frontmatter
// keys / heading-only nodes (e.g. when an old payload is cached or a
// caller bypassed the server's exclude_kinds default).
const CANVAS_NOISE_KINDS: ReadonlySet<string> = new Set([
  'doc:frontmatter_key',
  'doc_frontmatter',
  'doc:heading',
  'doc_heading',
]);

// Convert a raw export payload into a graphology Graph suitable for
// Sigma.js. Initial coordinates are random in [-1, 1] — ForceAtlas2
// will settle them on mount.
export function buildGraph(
  payload: ApiGraphPayload,
  opts: { visibleKinds?: Set<string>; visibleEdgeTypes?: Set<string> } = {},
): Graph<SigmaNodeAttrs, SigmaEdgeAttrs> {
  const graph = new Graph<SigmaNodeAttrs, SigmaEdgeAttrs>({ multi: true });

  const allNodes = payload.nodes ?? [];
  // Drop noise nodes BEFORE wiring edges so we never reference a uid
  // that won't be added to the graph.
  const nodes = allNodes.filter((n) => !CANVAS_NOISE_KINDS.has(n.kind));
  const edges = payload.edges ?? [];

  for (const n of nodes) {
    if (!n.uid) continue;
    // Normalise legacy colon-prefixed kinds (`code:function`,
    // `doc:heading`) to the canonical short forms before the
    // visibility check — otherwise the legend toggles match nothing
    // and the canvas renders empty.
    const normalKind = normalizeKind(n.kind);
    const kindVisible = opts.visibleKinds
      ? opts.visibleKinds.has(normalKind)
      : true;
    if (graph.hasNode(n.uid)) continue;
    graph.addNode(n.uid, {
      x: Math.random() * 2 - 1,
      y: Math.random() * 2 - 1,
      size: normalKind === 'folder' || normalKind === 'file' ? 6 : 4,
      color: kindColor(n.kind),
      label: n.label || n.uid,
      kind: normalKind,
      filePath: n.file_path ?? undefined,
      startLine: n.start_line ?? undefined,
      hidden: !kindVisible,
    });
  }

  for (const e of edges) {
    if (!graph.hasNode(e.source_uid) || !graph.hasNode(e.target_uid)) continue;
    const typeVisible = opts.visibleEdgeTypes
      ? opts.visibleEdgeTypes.has(e.edge_type)
      : true;
    const key = `${e.source_uid}->${e.target_uid}:${e.edge_type}`;
    if (graph.hasEdge(key)) continue;
    try {
      graph.addEdgeWithKey(key, e.source_uid, e.target_uid, {
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
    if (!adjacency.has(e.source_uid)) adjacency.set(e.source_uid, new Set());
    if (!adjacency.has(e.target_uid)) adjacency.set(e.target_uid, new Set());
    adjacency.get(e.source_uid)!.add(e.target_uid);
    adjacency.get(e.target_uid)!.add(e.source_uid);
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
    (e) => visited.has(e.source_uid) && visited.has(e.target_uid),
  );
  return { nodes, edges };
}
