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

// Tokens chosen to stay legible on the #11151c canvas background.
export const NODE_COLORS: Record<NodeKind, string> = {
  folder: '#fbbf24',
  file: '#60a5fa',
  module: '#38bdf8',
  class: '#a78bfa',
  method: '#c084fc',
  function: '#7fd4a0',
  variable: '#f472b6',
  interface: '#34d399',
  import_: '#94a3b8',
  route: '#f97316',
  tool: '#facc15',
  mcp_tool: '#eab308',
  event: '#22d3ee',
  task: '#ffa64d',
  doc_file: '#5aa8ff',
  doc_heading: '#93c5fd',
  doc_frontmatter: '#60a5fa',
  doc_external: '#64748b',
  rule: '#ef4444',
  skill: '#c68fff',
  contract: '#14b8a6',
  community: '#f9a8d4',
  hook: '#fb923c',
  identifier: '#cbd5f5',
  unknown: '#6b7280',
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
