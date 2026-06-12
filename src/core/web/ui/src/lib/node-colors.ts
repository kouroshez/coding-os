// NodeKind → color map. Values mirror core/graph_os/types.py::NodeKind
// (S3 canonical short forms). Kept in sync with the legacy color
// scheme from core/graph_os/viewer/template.py for continuity.

import { useThemeStore, type Theme } from '@/store/theme-store';

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

// Cortex graph palette v3 — VIVID + THEME-AWARE. v2 was tuned for the
// dark canvas (mid-lightness) and read washed/lifeless on the white
// canvas. Now two palettes: DARK = bright-saturated (pops on near-black),
// LIGHT = deep-saturated (pops on white), warm structure so the canvas
// reads alive. Same 7 hue families + bold within-family lightness steps.
// Both ΔE-verified: every common-vs-common kind pair ≥18 ΔE76
// (src/core/web/ui/scripts/palette_dual.py). SSOT: design-system.md §4.
export const NODE_COLORS: Record<NodeKind, string> = {
  // ─── STRUCTURE — warm amber / bronze / tan (alive) ───
  folder: '#E8A24A',
  module: '#B0742C',
  file: '#B58A6E',
  // ─── REFS — warm slate (recede) ───
  import_: '#8A8276',
  identifier: '#A39A8A',
  // ─── CODE-DEFS — indigo → violet [BRAND] ───
  class: '#8B8FF4',
  interface: '#5B5FE0',
  variable: '#B9BBF9',
  function: '#B07CF0',
  method: '#D0A6FF',
  // ─── API-SURFACE — azure / cyan ───
  route: '#4C9DF0',
  mcp_tool: '#2DD4D4',
  tool: '#79E6D8',
  contract: '#3B82F6',
  event: '#6FC0FF',
  // ─── DOCS — green / teal ───
  doc_file: '#34D399',
  doc_heading: '#86E05A',
  doc_frontmatter: '#BCE8A0',
  doc_external: '#2DD4BF',
  // ─── GOVERNANCE — magenta / pink / rose ───
  rule: '#D070D0',
  skill: '#F25FBE',
  task: '#FF85C2',
  hook: '#FF5C7A',
  // ─── ANALYSIS — orange ───
  community: '#F2913D',
  // ─── DEFAULT — gray ───
  unknown: '#9AA0A8',
};

// LIGHT canvas — deep, saturated (ink-on-paper). Same families/order.
export const NODE_COLORS_LIGHT: Record<NodeKind, string> = {
  folder: '#D08A28',
  module: '#7A4E16',
  file: '#6E5848',
  import_: '#8B8270',
  identifier: '#5F5A50',
  class: '#4B45C8',
  interface: '#322C9E',
  variable: '#6258D8',
  function: '#6A23BE',
  method: '#A064E0',
  route: '#1565C0',
  mcp_tool: '#0E8A9E',
  tool: '#1A9DB5',
  contract: '#0C4F8A',
  event: '#1F7FD0',
  doc_file: '#0E8A5E',
  doc_heading: '#4A8C24',
  doc_frontmatter: '#6B9E36',
  doc_external: '#0E7E7E',
  rule: '#A81C9E',
  skill: '#C21F72',
  task: '#C44D9E',
  hook: '#C71F4E',
  community: '#C26516',
  unknown: '#8B8270',
};

export const ALL_KINDS: NodeKind[] = Object.keys(NODE_COLORS) as NodeKind[];

// ─── Root / focal anchor (RESERVED — not a categorical kind) ──────────
// The graph's structural origin (`folder:.`) gets a focal style OUTSIDE
// the kind palette so it never blends into a category hue — the
// canonical enterprise focus-node pattern (KeyLines / ReGraph /
// Linkurious). It wears the brand-logomark iris weight (#4F46E5, the
// same indigo the wordmark uses) so the anchor reads as "the project's
// home". Theme-independent: the logomark references one iris weight on
// both canvases. SSOT note: docs/engineering/design-system.md §4.
export const ROOT_UIDS: ReadonlySet<string> = new Set(['folder:.', 'folder:']);
export const ROOT_COLOR = '#4F46E5';
export const isRootUid = (uid: string): boolean => ROOT_UIDS.has(uid);

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

// Theme-aware: pass a theme, or omit to read the live theme-store (so DOM
// legends/panels follow the current theme at render). The graph canvas
// recolors on toggle via the subscription in useSigma.
export const kindColor = (kind: string | null | undefined, theme?: Theme): string => {
  const palette =
    (theme ?? useThemeStore.getState().theme) === 'light' ? NODE_COLORS_LIGHT : NODE_COLORS;
  return palette[normalizeKind(kind)];
};
