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

// Tokens chosen to stay legible on the cream paper canvas
// (--cos-bg ≈ #f4efe1). Brand anchors: Mocha 500 (#FF7A3D, primary
// orange) for the most-clicked code kinds, Mocha 700 (#C84B16) for
// emphasis, Ink 600 (#6B504A) for muted tooling. Saturation kept high
// so 4-6px node dots stay readable, lightness kept ≤ 65% so labels
// don't blow out.
export const NODE_COLORS: Record<NodeKind, string> = {
  // Structure: warm browns from the Ink ramp.
  folder: '#8B5A2B',
  file: '#3A2925',
  module: '#6B504A',
  // Code kinds anchored on Mocha (orange) family.
  class: '#FF7A3D',
  method: '#FFA468',
  function: '#C84B16',
  variable: '#B19A93',
  interface: '#3A7A3A',
  import_: '#8a8378',
  // Cross-cutting / framework concepts.
  route: '#2C5AA0',
  tool: '#C0392B',
  mcp_tool: '#8B2318',
  event: '#0D7377',
  task: '#3A7A3A',
  // Docs: muted blues so prose nodes don't compete with code.
  doc_file: '#2C5AA0',
  doc_heading: '#5A7CA8',
  doc_frontmatter: '#8593a8',
  doc_external: '#6B665E',
  // Governance: red ramp for rules, plum for skills.
  rule: '#8B2318',
  skill: '#7A3A7A',
  contract: '#3A7A7A',
  community: '#C0719B',
  hook: '#D96C2C',
  identifier: '#6B665E',
  unknown: '#B19A93',
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
