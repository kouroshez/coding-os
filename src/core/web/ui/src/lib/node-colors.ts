// NodeKind → color map. Values mirror core/graph_os/types.py::NodeKind
// (S3 canonical short forms). Kept in sync with the legacy color
// scheme from core/graph_os/viewer/template.py for continuity.

export type NodeKind =
  | 'folder'
  | 'file'
  | 'module'
  | 'class'
  | 'method'
  | 'function'
  | 'variable'
  | 'interface'
  | 'import_'
  | 'route'
  | 'tool'
  | 'mcp_tool'
  | 'event'
  | 'task'
  | 'doc_file'
  | 'doc_heading'
  | 'doc_frontmatter'
  | 'doc_external'
  | 'rule'
  | 'skill'
  | 'contract'
  | 'community'
  | 'hook'
  | 'identifier'
  | 'unknown';

// Semantic colour groups (TASK-018). 25 kinds → 8 hue families so the
// canvas reads at a glance: brown=structure, orange=code-defs (BRAND
// Mocha), gray=code-refs, blue=API-surface, teal=docs, purple=governance,
// gold=analysis. Within each family kinds vary by lightness to stay
// distinguishable at 4-6 px dot size. Saturation high, lightness ≤ 65 %
// so labels render cleanly on the cream paper background (--cos-bg ≈
// #f4efe1). ΔE ≥ 10 across cross-group neighbours.
export const NODE_COLORS: Record<NodeKind, string> = {
  // ─── STRUCTURE (filesystem) — warm browns ───
  folder: '#8B5A2B',
  file: '#3A2925',
  module: '#6B504A',
  // ─── CODE-DEFS (symbol declarations) — Mocha orange/red [BRAND] ───
  class: '#FF7A3D',
  method: '#FFA468',
  function: '#C84B16',
  variable: '#E89C6B',
  interface: '#A53C12',
  // ─── CODE-REFS (references / imports) — neutral gray ───
  import_: '#A8A29B',
  identifier: '#736C66',
  // ─── API-SURFACE (external contracts) — blue family ───
  route: '#1E5FBA',
  mcp_tool: '#0D47A1',
  tool: '#3F7DC9',
  contract: '#1565C0',
  event: '#0277BD',
  // ─── DOCS (prose) — teal / cyan family ───
  doc_file: '#00838F',
  doc_heading: '#26A69A',
  doc_frontmatter: '#80CBC4',
  doc_external: '#4DB6AC',
  // ─── GOVERNANCE (coding-os meta) — purple / magenta family ───
  rule: '#6A1B9A',
  skill: '#9C27B0',
  hook: '#C2185B',
  task: '#7B1FA2',
  // ─── ANALYSIS (rare meta nodes) — gold ───
  community: '#F9A825',
  // ─── DEFAULT — light gray ───
  unknown: '#B0B0B0',
};

export const ALL_KINDS: NodeKind[] = Object.keys(NODE_COLORS) as NodeKind[];

// Map legacy colon-prefixed kinds emitted by the extractors
// (`code:function`, `doc:heading`) to the canonical short form used
// by NodeKind / visibleKinds.  Mirrors `_LEGACY_KIND_MAP` in
// core/graph_os/types.py — the SPA needs the same mapping because
// many nodes still carry the legacy form.
const LEGACY_KIND_MAP: Record<string, NodeKind> = {
  'code:folder': 'folder',
  'code:file': 'file',
  'code:module': 'module',
  'code:class': 'class',
  'code:method': 'method',
  'code:function': 'function',
  'code:variable': 'variable',
  'code:interface': 'interface',
  'code:import': 'import_',
  'doc:file': 'doc_file',
  'doc:heading': 'doc_heading',
  'doc:frontmatter_key': 'doc_frontmatter',
  'doc:external': 'doc_external',
  'cos:route': 'route',
  'cos:mcp_tool': 'mcp_tool',
  'cos:tool': 'tool',
  'cos:event': 'event',
  'cos:hook': 'hook',
  'cos:skill': 'skill',
  'cos:rule': 'rule',
  'cos:contract': 'contract',
  'cos:identifier': 'identifier',
  'cos:community': 'community',
  'task:file': 'task',
  // Already-canonical short forms map to themselves so callers don't
  // need to know which form a node carries.
  ...Object.fromEntries(ALL_KINDS.map((k) => [k, k])),
};

/** Normalise any extractor kind (legacy or canonical) to the short form. */
export const normalizeKind = (kind: string | null | undefined): NodeKind => {
  if (!kind) return 'unknown';
  return LEGACY_KIND_MAP[kind.toLowerCase()] ?? 'unknown';
};

export const kindColor = (kind: string | null | undefined): string => {
  return NODE_COLORS[normalizeKind(kind)];
};
