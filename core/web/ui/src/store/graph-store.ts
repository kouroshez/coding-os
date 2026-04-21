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

interface GraphStoreState {
  selectedRootUid: string | null;
  selectedNodeUid: string | null;
  depth: DepthFilter;
  visibleKinds: Set<NodeKind>;
  visibleEdgeTypes: Set<string>;

  setRoot: (uid: string | null) => void;
  setSelectedNode: (uid: string | null) => void;
  setDepth: (d: DepthFilter) => void;
  toggleKind: (k: NodeKind) => void;
  setAllKinds: (visible: boolean) => void;
  toggleEdgeType: (t: string) => void;
}

export const useGraphStore = create<GraphStoreState>((set) => ({
  selectedRootUid: null,
  selectedNodeUid: null,
  depth: 2,
  visibleKinds: new Set<NodeKind>(ALL_KINDS),
  visibleEdgeTypes: new Set<string>(DEFAULT_EDGE_TYPES),

  setRoot: (uid) => set({ selectedRootUid: uid, selectedNodeUid: null }),
  setSelectedNode: (uid) => set({ selectedNodeUid: uid }),
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
}));
