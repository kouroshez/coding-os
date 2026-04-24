import { useGraphStore, type DepthFilter } from '@/store/graph-store';

const OPTIONS: DepthFilter[] = [1, 2, 3, 'all'];

// Depth slider — user-facing control for client-side BFS depth.
// Re-renders the canvas when changed; no extra server round-trip.
export default function DepthSlider() {
  const depth = useGraphStore((s) => s.depth);
  const setDepth = useGraphStore((s) => s.setDepth);

  return (
    <fieldset className="flex items-center gap-2 text-xs">
      <legend className="sr-only">BFS depth</legend>
      <span className="text-[var(--cos-muted)]">depth</span>
      {OPTIONS.map((d) => {
        const active = d === depth;
        return (
          <button
            key={String(d)}
            type="button"
            onClick={() => setDepth(d)}
            aria-pressed={active}
            className={[
              'rounded border px-2 py-0.5',
              active
                ? 'border-[var(--cos-accent)] bg-[var(--cos-accent)]/15 text-[var(--cos-accent)]'
                : 'border-[var(--cos-border)] text-[var(--cos-text)] hover:bg-[var(--cos-panel)]',
            ].join(' ')}
          >
            {d}
          </button>
        );
      })}
    </fieldset>
  );
}
