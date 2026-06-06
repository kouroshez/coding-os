import { create } from 'zustand';
import type { NodeKind } from '@/lib/node-colors';
import { ALL_KINDS } from '@/lib/node-colors';

// Default edge types advertised by the S3 contracts surface; the filter
// panel lets the user toggle each on/off. This list is intentionally
// generous — unknown types in the payload default-visible.
export const DEFAULT_EDGE_TYPES = [
  'contains',
  'imports',
  'calls',
  'extends',
  'implements',
  'references_doc',
  'references',
  'defines_route',
  'dispatches',
  'handles_route',
  'handles_tool',
  'handles_event',
  'awaits',
  'accesses_field',
  'member_of_community',
] as const;

export type DepthFilter = 1 | 2 | 3 | 'all';

// view-mode tabs that drive the backend `cos_graph_export`
// blend selection — see `_AUTO_BLEND_BUCKETS` in graph_os/tools/graph.py.
export type ViewMode = 'auto' | 'containment' | 'dependencies' | 'processes';

interface GraphStoreState {
  selectedRootUid: string | null;
  selectedNodeUid: string | null;
  viewMode: ViewMode;
  depth: DepthFilter;
  visibleKinds: Set<NodeKind>;
  visibleEdgeTypes: Set<string>;
  searchQuery: string;

  setRoot: (uid: string | null) => void;
  setSelectedNode: (uid: string | null) => void;
  setViewMode: (m: ViewMode) => void;
  setDepth: (d: DepthFilter) => void;
  toggleKind: (k: NodeKind) => void;
  setAllKinds: (visible: boolean) => void;
  toggleEdgeType: (t: string) => void;
  setSearchQuery: (q: string) => void;
}

export const useGraphStore = create<GraphStoreState>((set) => ({
  selectedRootUid: null,
  selectedNodeUid: null,
  viewMode: 'auto',
  depth: 2,
  visibleKinds: new Set<NodeKind>(ALL_KINDS),
  visibleEdgeTypes: new Set<string>(DEFAULT_EDGE_TYPES),
  searchQuery: '',

  // when a root is picked, mirror it into selectedNodeUid
  // so the right-pane Inspector opens for it.  Previously the inspector
  // stayed on the placeholder until the user separately clicked a node
  // on the canvas — confusing UX, especially when picking from the
  // left tree.
  setRoot: (uid) => set({ selectedRootUid: uid, selectedNodeUid: uid }),
  setSelectedNode: (uid) => set({ selectedNodeUid: uid }),
  setViewMode: (viewMode) => set({ viewMode }),
  setDepth: (depth) => set({ depth }),

  toggleKind: (k) =>
    set((s) => {
      const next = new Set(s.visibleKinds);
      if (next.has(k)) {
        next.delete(k);
      } else {
        next.add(k);
      }
      return { visibleKinds: next };
    }),

  setAllKinds: (visible) =>
    set(() => ({ visibleKinds: new Set<NodeKind>(visible ? ALL_KINDS : []) })),

  toggleEdgeType: (t) =>
    set((s) => {
      const next = new Set(s.visibleEdgeTypes);
      if (next.has(t)) {
        next.delete(t);
      } else {
        next.add(t);
      }
      return { visibleEdgeTypes: next };
    }),

  setSearchQuery: (searchQuery) => set({ searchQuery }),
}));
