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

// Cortex graph palette v2 — MAXIMUM DISTINCTION on the dark canvas.
// Rule: across families = a distinct HUE region; within a family = BOLD
// LIGHTNESS steps. v1 varied hue subtly at equal lightness, so
// class/method/function (and the azure API cluster) read as one dot at
// 4-6 px. 7 hue anchors: structure=amber · code-defs=indigo→violet ·
// refs=gray (recede) · api=cyan/teal · docs=green · governance=
// magenta/pink · analysis=orange. Verified: every common-vs-common kind
// pair ≥18 ΔE76 apart (pairwise CIE-Lab check); only the de-emphasized
// gray refs cluster, by design. SSOT: docs/engineering/design-system.md §4.
export const NODE_COLORS: Record<NodeKind, string> = {
  // ─── STRUCTURE — amber / gold ───
  folder: '#F4B63E',
  module: '#C0792E',
  // ─── REFS + file — neutral gray (ambient, recede) ───
  file: '#C2C9D6',
  identifier: '#7C8696',
  import_: '#4E5666',
  // ─── CODE-DEFS — indigo → violet [BRAND] ───
  class: '#6D7BF7',
  interface: '#3B45C8',
  variable: '#AEB6FF',
  function: '#B15CF5',
  method: '#D9A6FF',
  // ─── API-SURFACE — cyan / teal ───
  route: '#16A6C0',
  mcp_tool: '#15CBB4',
  tool: '#79E6D8',
  contract: '#0E6F8C',
  event: '#7AD4FF',
  // ─── DOCS — green ───
  doc_file: '#3FB950',
  doc_heading: '#86E05A',
  doc_frontmatter: '#BCE8A0',
  doc_external: '#2E9E6E',
  // ─── GOVERNANCE — magenta / pink / rose ───
  rule: '#D070D0',
  skill: '#F25FBE',
  task: '#FF85C2',
  hook: '#FF5C7A',
  // ─── ANALYSIS — orange ───
  community: '#F2761D',
  // ─── DEFAULT — gray ───
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
