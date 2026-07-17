import Graph from 'graphology';
import { kindColor, normalizeKind, isRootUid, ROOT_COLOR, ROOT_UIDS } from '@/lib/node-colors';

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

export interface ApiGraphMeta {
  node_count?: number;
  edge_count?: number;
  max_nodes_requested?: number;
  max_nodes_effective?: number;
  max_hops_effective?: number | null;
  result_truncated?: boolean;
}

export interface ApiGraphPayload {
  format?: string;
  nodes?: ApiNode[];
  edges?: ApiEdge[];
  meta?: ApiGraphMeta;
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
  forceLabel?: boolean;
  type?: string;
  image?: string;
}

export interface SigmaEdgeAttrs {
  size: number;
  color: string;
  edgeType: string;
  hidden?: boolean;
  weight?: number;
}

// client-side noise filter — keeps the canvas focused on
// real navigation targets even when the backend returns frontmatter
// keys / heading-only nodes (e.g. when an old payload is cached or a
// caller bypassed the server's exclude_kinds default).
const CANVAS_NOISE_KINDS: ReadonlySet<string> = new Set([
  'doc:frontmatter_key',
  'doc_frontmatter',
  'doc:heading',
  'doc_heading',
]);

// TASK-407 — focus+context community-map styling (InfraNodus / Bloom
// default for the no-root home). In `processes` mode the synthetic
// `community` nodes are the FOCUS (forced label, full group color, hub
// size) and their member nodes are CONTEXT (de-emphasised: muted color +
// reduced size) so the canvas reads as a labelled subsystem map instead
// of a flat blend sample. SSOT: docs/engineering/hub-architecture.md.
const MEMBER_DEEMPHASIS_ALPHA = '88'; // ~53% opacity hex suffix
const COMMUNITY_NODE_SIZE = 14;
const MEMBER_DEEMPHASIS_SIZE = 3;

// Blend a 6-digit hex color toward muted by appending an alpha suffix.
// Sigma's WebGL renderer honours 8-digit hex (#RRGGBBAA).
function mute(color: string): string {
  return /^#[0-9a-fA-F]{6}$/.test(color) ? `${color}${MEMBER_DEEMPHASIS_ALPHA}` : color;
}

// Convert a raw export payload into a graphology Graph suitable for
// Sigma.js. Initial coordinates are random in [-1, 1] — ForceAtlas2
// will settle them on mount.
export function buildGraph(
  payload: ApiGraphPayload,
  opts: {
    visibleKinds?: Set<string>;
    visibleEdgeTypes?: Set<string>;
    mode?: string;
  } = {},
): Graph<SigmaNodeAttrs, SigmaEdgeAttrs> {
  const graph = new Graph<SigmaNodeAttrs, SigmaEdgeAttrs>({ multi: true });

  const allNodes = payload.nodes ?? [];
  // Drop noise nodes BEFORE wiring edges so we never reference a uid
  // that won't be added to the graph.
  const nodes = allNodes.filter((n) => !CANVAS_NOISE_KINDS.has(n.kind));
  const edges = payload.edges ?? [];

  const degree = new Map<string, number>();
  for (const e of edges) {
    if (!e.source_uid || !e.target_uid) continue;
    degree.set(e.source_uid, (degree.get(e.source_uid) ?? 0) + 1);
    degree.set(e.target_uid, (degree.get(e.target_uid) ?? 0) + 1);
  }
  // Repo-root anchor — extractor emits exactly one of these. Always
  // dominates the canvas (size + reserved focal color + home glyph +
  // label) so the viewer's eye lands on the centre of importance.
  // ROOT_UIDS / ROOT_COLOR / isRootUid are imported from node-colors so
  // the build path and the theme-recolor path (useSigma) agree.
  // Top-K-by-degree get an emphasis tier (label + size bump). K scales
  // with graph size — five labels make sense on a 200-node subgraph;
  // a 20K-node overview needs more but capped well below "every
  // semantic kind with deg≥2" (which used to force ~thousands of
  // labels and turned the canvas into the reported black blob).
  const TOP_K = Math.min(40, Math.max(5, Math.round(Math.sqrt(nodes.length))));
  const topByDegree = [...degree.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, TOP_K)
    .map(([uid]) => uid);
  const TOP_DEGREE: Set<string> = new Set(topByDegree);
  // TASK-407: in the community map the synthetic `community` headers are
  // the focus tier and their members are de-emphasised context.
  const isCommunityMap = opts.mode === 'processes';
  const sizeFor = (uid: string, kind: string): number => {
    if (ROOT_UIDS.has(uid)) return 32;             // γ·root_bonus
    if (isCommunityMap) {
      if (kind === 'community') return COMMUNITY_NODE_SIZE;
      // Member nodes recede — a small uniform dot so the labelled
      // community groups dominate the canvas (focus+context).
      return MEMBER_DEEMPHASIS_SIZE;
    }
    const base = kind === 'folder' ? 5 : kind === 'file' ? 4 : kind === 'module' ? 3.5 : 2;
    const d = degree.get(uid) ?? 0;
    const sized = base + Math.log2(d + 1) * 2.6;
    const hubBoost = TOP_DEGREE.has(uid) ? 1.4 : 1.0;
    return Math.min(28, sized * hubBoost);
  };
  // forceLabel was so permissive that any semantic node with deg≥2 got
  // a label rendered ignoring the camera zoom — on a dense overview
  // that's thousands of forced labels and the canvas becomes
  // unreadable. Restrict to the curated top-K hubs + the structural
  // root; everything else relies on Sigma's zoom-aware label budget
  // (labelDensity / labelRenderedSizeThreshold) so labels only show
  // when there's room.
  const labelForceFor = (uid: string, kind: string): boolean => {
    if (ROOT_UIDS.has(uid)) return true;
    // TASK-407: community headers always carry their group label so the
    // map reads as named subsystems; members stay zoom-budget-only.
    if (isCommunityMap) return kind === 'community';
    if (TOP_DEGREE.has(uid)) return true;
    return false;
  };

  const createSvgIcon = (pathData: string) => 
    `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${pathData}"/></svg>`)}`;

  // Root anchor glyph — a home inside a halo ring (white strokes on the
  // reserved iris disc). Distinct from the generic folder icon so the
  // project origin is unmistakable at a glance (enterprise focus-node
  // pattern). Ring at r=10 sits just inside the node-image clip radius.
  const ROOT_ICON =
    `data:image/svg+xml;utf8,${encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M7.5 12.2 12 8l4.5 4.2"/><path d="M8.6 11.3V16h6.8v-4.7"/></svg>`,
    )}`;

  const ICONS: Record<string, string> = {
    folder: createSvgIcon('M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z'),
    file: createSvgIcon('M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M16 13H8 M16 17H8 M10 9H8'),
    module: createSvgIcon('M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z M3.27 6.96L12 12.01l8.73-5.05 M12 22.08V12'),
    database: createSvgIcon('M12 5c-4.42 0-8 1.79-8 4s3.58 4 8 4 8-1.79 8-4-3.58-4-8-4z M4 9v6c0 2.21 3.58 4 8 4s8-1.79 8-4V9 M4 15v6c0 2.21 3.58 4 8 4s8-1.79 8-4v-6'),
    component: createSvgIcon('M12 2l9 4.9V17L12 22l-9-4.9V7z M12 22v-10 M12 12L3 7 M12 12l9-5'), // Cube
    class: createSvgIcon('M20 16V7a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2z M8 21h8 M12 17v4'), // Monitor
  };

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

    const root = isRootUid(n.uid);
    const image = root ? ROOT_ICON : ICONS[normalKind];

    // TASK-407: focus tier = community headers (full group color);
    // context tier = members (muted) in the community-map home.
    const isMember = isCommunityMap && normalKind !== 'community';
    const baseColor = root ? ROOT_COLOR : kindColor(n.kind);
    const color = isMember ? mute(baseColor) : baseColor;

    graph.addNode(n.uid, {
      x: Math.random() * 2 - 1,
      y: Math.random() * 2 - 1,
      size: sizeFor(n.uid, normalKind),
      color,
      label: n.label || n.uid,
      kind: normalKind,
      filePath: n.file_path ?? undefined,
      startLine: n.start_line ?? undefined,
      hidden: !kindVisible,
      forceLabel: labelForceFor(n.uid, normalKind),
      // Members drop their icon image so the muted dot reads as context,
      // not a competing focus node; community headers have no icon anyway.
      type: image && !isMember ? 'image' : 'circle',
      image: image && !isMember ? image : undefined,
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
        size: edgeSize(e.edge_type),
        color: edgeColor(e.edge_type),
        edgeType: e.edge_type,
        hidden: !typeVisible,
        weight: edgeWeight(e.edge_type),
      });
    } catch {
      // duplicate — ignore
    }
  }

  return graph;
}

// Edge styling (Cortex) — edge families echo the node hue system but
// dimmer/desaturated so nodes stay the focus: structure=steel,
// calls/construct=Iris, imports/api=azure, type/docs=teal, inherit=violet,
// blocks=danger. SSOT: docs/engineering/design-system.md.
const EDGE_PALETTE: Record<string, { color: string; size: number }> = {
  contains: { color: '#3A4150', size: 1.2 },
  calls: { color: '#7C82F2', size: 1.0 },
  constructs: { color: '#6E72E8', size: 1.1 },
  imports: { color: '#3B82F6', size: 0.9 },
  inherits_from: { color: '#B98AF0', size: 1.3 },
  implements: { color: '#B98AF0', size: 1.3 },
  extends: { color: '#B98AF0', size: 1.3 },
  has_param_type: { color: '#14B8A6', size: 0.7 },
  returns_type: { color: '#14B8A6', size: 0.7 },
  field_of_type: { color: '#14B8A6', size: 0.7 },
  is_decorated_by: { color: '#6E7686', size: 0.7 },
  references_doc: { color: '#2DD4BF', size: 0.8 },
  cites_heading: { color: '#2DD4BF', size: 0.8 },
  links_to: { color: '#2DD4BF', size: 0.8 },
  handles_route: { color: '#4C9DF0', size: 1.1 },
  handles_tool: { color: '#4C9DF0', size: 1.1 },
  handles_event: { color: '#4C9DF0', size: 1.1 },
  dispatches: { color: '#5FB0F5', size: 1.1 },
  defines_route: { color: '#4C9DF0', size: 1.1 },
  awaits: { color: '#A6A9F7', size: 0.9 },
  blocks: { color: '#F2576B', size: 1.2 },
  depends_on: { color: '#565E6C', size: 0.9 },
  re_exports: { color: '#646E7E', size: 0.7 },
  member_of_community: { color: '#C77DFF', size: 0.6 },
};

function edgeColor(edgeType: string): string {
  return EDGE_PALETTE[edgeType]?.color ?? '#3A4150';
}

function edgeSize(edgeType: string): number {
  return EDGE_PALETTE[edgeType]?.size ?? 0.8;
}

function edgeWeight(edgeType: string): number {
  // Strong structural bonds pull nodes together tightly in ForceAtlas2
  if (['contains', 'defines_route'].includes(edgeType)) return 20;
  if (['inherits_from', 'implements', 'extends'].includes(edgeType)) return 5;
  // Weak operational bonds allow nodes to breathe
  return 1;
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
