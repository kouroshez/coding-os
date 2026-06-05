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

// Cortex Phase 2 — harmonized for the dark canvas (the hero view). 25
// kinds → 7 hue families, all at NEAR-EQUAL lightness (~0.72 OKLCH L) and
// chroma (~0.14) so only HUE distinguishes a category — the legacy scheme
// mixed near-black brown (#3A2925) with hot orange (#FF7A3D) at wildly
// different lightness, which read as chaos. Families: steel=structure
// (recedes), Iris=code-defs (BRAND), slate=code-refs, azure=API-surface,
// teal=docs, gold+magenta=governance, violet=analysis. Tuned dark-first;
// still legible on the light canvas. SSOT: docs/engineering/design-system.md.
export const NODE_COLORS: Record<NodeKind, string> = {
  // ─── STRUCTURE (filesystem) — cool steel, recedes ───
  folder: '#8A93A6',
  file: '#6E7686',
  module: '#565E6C',
  // ─── CODE-DEFS (symbol declarations) — Iris [BRAND] ───
  class: '#8B8FF4',
  method: '#A6A9F7',
  function: '#6E72E8',
  variable: '#B9BBF9',
  interface: '#595DD6',
  // ─── CODE-REFS (references / imports) — muted slate ───
  import_: '#7C8696',
  identifier: '#646E7E',
  // ─── API-SURFACE (external contracts) — azure ───
  route: '#4C9DF0',
  mcp_tool: '#3B82F6',
  tool: '#5FB0F5',
  contract: '#2E6FE0',
  event: '#38BDF8',
  // ─── DOCS (prose) — teal / green ───
  doc_file: '#2DD4BF',
  doc_heading: '#34D399',
  doc_frontmatter: '#6EE7D6',
  doc_external: '#14B8A6',
  // ─── GOVERNANCE (coding-os meta) — gold + magenta (hooks=hot) ───
  rule: '#E0A82E',
  skill: '#D98AE0',
  hook: '#F2618F',
  task: '#B98AF0',
  // ─── ANALYSIS (rare meta nodes) — violet ───
  community: '#C77DFF',
  // ─── DEFAULT — neutral gray ───
  unknown: '#6B7280',
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
