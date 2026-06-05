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
  const searchQuery = useGraphStore((s) => s.searchQuery);
  const setSearchQuery = useGraphStore((s) => s.setSearchQuery);

  return (
    <div className="flex flex-col gap-3 text-xs">
      <section aria-label="Search nodes" className="mb-1">
        <h3 className="mb-1 font-semibold uppercase tracking-wide text-[var(--cos-muted)]">Search</h3>
        <div className="relative">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by path/name..."
            dir="auto"
            className="w-full rounded-lg border border-white/10 bg-white/5 py-1.5 pl-2.5 pr-8 text-xs text-[var(--cos-text)] placeholder-white/30 shadow-inner outline-none transition-all duration-300 focus:border-[var(--cos-accent)] focus:bg-white/10 focus:shadow-[0_0_8px_rgba(217,70,239,0.25)]"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[10px] text-white/40 hover:text-white/80"
              title="Clear search"
            >
              ✕
            </button>
          )}
        </div>
      </section>

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
