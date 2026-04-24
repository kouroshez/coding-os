import { useGraphStore } from '@/store/graph-store';
import { ALL_KINDS, kindColor } from '@/lib/node-colors';
import { DEFAULT_EDGE_TYPES } from '@/store/graph-store';

// Two-column filter bar — NodeKind tickboxes and edge-type tickboxes.
// Both filter the Graphology graph in-memory (see graph-adapter).
export default function FilterBar() {
  const visibleKinds = useGraphStore((s) => s.visibleKinds);
  const toggleKind = useGraphStore((s) => s.toggleKind);
  const setAllKinds = useGraphStore((s) => s.setAllKinds);
  const visibleEdgeTypes = useGraphStore((s) => s.visibleEdgeTypes);
  const toggleEdgeType = useGraphStore((s) => s.toggleEdgeType);

  return (
    <div className="flex flex-col gap-3 text-xs">
      <section aria-label="Node kinds">
        <div className="mb-1 flex items-center justify-between">
          <h3 className="font-semibold uppercase tracking-wide text-[var(--cos-muted)]">Kinds</h3>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setAllKinds(true)}
              className="text-[var(--cos-accent)] hover:underline"
            >
              all
            </button>
            <button
              type="button"
              onClick={() => setAllKinds(false)}
              className="text-[var(--cos-muted)] hover:underline"
            >
              none
            </button>
          </div>
        </div>
        <ul className="grid grid-cols-2 gap-1">
          {ALL_KINDS.map((k) => {
            const checked = visibleKinds.has(k);
            return (
              <li key={k}>
                <label className="flex cursor-pointer items-center gap-2">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleKind(k)}
                    aria-label={`Toggle ${k}`}
                  />
                  <span
                    className="inline-block h-2 w-2 rounded-sm"
                    style={{ background: kindColor(k) }}
                    aria-hidden
                  />
                  <span>{k}</span>
                </label>
              </li>
            );
          })}
        </ul>
      </section>

      <section aria-label="Edge types">
        <h3 className="mb-1 font-semibold uppercase tracking-wide text-[var(--cos-muted)]">Edges</h3>
        <ul className="grid grid-cols-2 gap-1">
          {DEFAULT_EDGE_TYPES.map((t) => (
            <li key={t}>
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={visibleEdgeTypes.has(t)}
                  onChange={() => toggleEdgeType(t)}
                  aria-label={`Toggle edge ${t}`}
                />
                <span>{t}</span>
              </label>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
