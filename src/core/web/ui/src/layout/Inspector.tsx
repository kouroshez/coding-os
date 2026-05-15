import { useGraphStore } from '@/store/graph-store';
import NodeInspector from '@/features/graph/NodeInspector';

// Right-pane inspector. Currently only the graph page feeds it via
// zustand; future pages (Board card detail, Cognition event zoom) can
// consume the same store or nest their own inspectors.
export default function Inspector() {
  const selectedUid = useGraphStore((s) => s.selectedNodeUid);

  if (!selectedUid) {
    return (
      <div className="flex h-full flex-col p-4 text-sm text-[var(--cos-faint)]">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
          Inspector
        </h2>
        <p>Click a node in the graph, a card on the board, or a trace event to inspect.</p>
      </div>
    );
  }

  return <NodeInspector uid={selectedUid} />;
}
