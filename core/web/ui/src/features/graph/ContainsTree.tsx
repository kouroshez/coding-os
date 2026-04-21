import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { useGraphStore } from '@/store/graph-store';
import { useApiGet } from '@/lib/hooks';
import { kindColor } from '@/lib/node-colors';
import type { ApiEdge, ApiGraphPayload, ApiNode } from './graph-adapter';

interface TreeNode {
  uid: string;
  kind: string;
  label: string;
  children: TreeNode[];
}

// Build a forest from contains-only edges. Any node with no incoming
// contains edge is a root (typically repo:root or the top folder).
function buildForest(payload: ApiGraphPayload): TreeNode[] {
  const nodes = new Map<string, ApiNode>();
  for (const n of payload.nodes ?? []) nodes.set(n.uid, n);

  const childrenOf = new Map<string, string[]>();
  const hasParent = new Set<string>();
  for (const e of payload.edges ?? []) {
    if (e.edge_type !== 'contains') continue;
    const list = childrenOf.get(e.source) ?? [];
    list.push(e.target);
    childrenOf.set(e.source, list);
    hasParent.add(e.target);
  }

  const mkNode = (uid: string, seen: Set<string>): TreeNode | null => {
    if (seen.has(uid)) return null;
    seen.add(uid);
    const meta = nodes.get(uid);
    if (!meta) return null;
    const children = (childrenOf.get(uid) ?? [])
      .map((c) => mkNode(c, seen))
      .filter((n): n is TreeNode => n !== null)
      .sort((a, b) => a.label.localeCompare(b.label));
    return {
      uid,
      kind: meta.kind,
      label: meta.label || meta.uid,
      children,
    };
  };

  const seen = new Set<string>();
  const roots: TreeNode[] = [];
  for (const uid of nodes.keys()) {
    if (hasParent.has(uid)) continue;
    const node = mkNode(uid, seen);
    if (node) roots.push(node);
  }
  return roots.sort((a, b) => a.label.localeCompare(b.label));
}

function TreeRow({
  node,
  depth,
  onSelect,
  selectedUid,
}: {
  node: TreeNode;
  depth: number;
  onSelect: (uid: string) => void;
  selectedUid: string | null;
}) {
  const [open, setOpen] = useState(depth < 1);
  const hasChildren = node.children.length > 0;
  const selected = selectedUid === node.uid;

  return (
    <li>
      <div
        className={[
          'flex cursor-pointer items-center gap-1 rounded px-1 py-0.5 text-xs',
          selected ? 'bg-[#1b3528] text-[#7fd4a0]' : 'hover:bg-[#1b1f27]',
        ].join(' ')}
        style={{ paddingLeft: depth * 10 + 2 }}
      >
        <button
          type="button"
          aria-label={open ? 'Collapse' : 'Expand'}
          className="flex h-4 w-4 items-center justify-center text-[#9ea4ae]"
          onClick={() => setOpen((v) => !v)}
          disabled={!hasChildren}
        >
          {hasChildren ? (
            open ? (
              <ChevronDown size={12} />
            ) : (
              <ChevronRight size={12} />
            )
          ) : (
            <span className="inline-block h-2 w-2" aria-hidden />
          )}
        </button>
        <button
          type="button"
          onClick={() => onSelect(node.uid)}
          className="flex min-w-0 flex-1 items-center gap-1 text-left"
          title={node.uid}
        >
          <span
            className="inline-block h-2 w-2 rounded-sm"
            style={{ background: kindColor(node.kind) }}
            aria-hidden
          />
          <span className="truncate">{node.label}</span>
        </button>
      </div>
      {hasChildren && open && (
        <ul>
          {node.children.map((c) => (
            <TreeRow
              key={c.uid}
              node={c}
              depth={depth + 1}
              onSelect={onSelect}
              selectedUid={selectedUid}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

// Left-pane CONTAINS spine tree. Clicking a row promotes it to the
// current graph root.
export default function ContainsTree() {
  const selectedRootUid = useGraphStore((s) => s.selectedRootUid);
  const setRoot = useGraphStore((s) => s.setRoot);

  const { data, isLoading, error } = useApiGet<ApiGraphPayload>(
    ['contains-tree'],
    '/api/graph/export',
    { format: 'json', edge_types: 'contains', max_nodes: 500 },
  );

  const forest = useMemo(() => (data ? buildForest(data) : []), [data]);

  // Filter out trivial leaves that mirror the edge payload — keep spine semantics:
  const visibleForest = useMemo(() => {
    return forest.filter(
      (n) => n.children.length > 0 || n.kind === 'folder' || n.kind === 'file',
    );
  }, [forest]);

  return (
    <section aria-label="Contains tree" className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-[#2a2f39] px-2 py-1 text-xs">
        <span className="font-semibold uppercase tracking-wide text-[#9ea4ae]">
          Contains spine
        </span>
        {selectedRootUid && (
          <button
            type="button"
            onClick={() => setRoot(null)}
            className="text-[#9ea4ae] hover:text-white"
            title="Clear root"
          >
            clear
          </button>
        )}
      </header>
      <div className="flex-1 overflow-auto p-1 cos-scroll">
        {isLoading && <p className="p-2 text-xs text-[#9ea4ae]">loading spine…</p>}
        {error && (
          <p className="p-2 text-xs text-rose-400" role="alert">
            {error.message}
          </p>
        )}
        {!isLoading && !error && visibleForest.length === 0 && (
          <p className="p-2 text-xs text-[#9ea4ae]">
            no CONTAINS edges in graph yet. Run <code>cos graph-reindex</code>.
          </p>
        )}
        <ul>
          {visibleForest.map((r) => (
            <TreeRow
              key={r.uid}
              node={r}
              depth={0}
              onSelect={setRoot}
              selectedUid={selectedRootUid}
            />
          ))}
        </ul>
      </div>
    </section>
  );
}

export type { ApiEdge };
