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
      <span className="text-[#9ea4ae]">depth</span>
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
                ? 'border-[#7fd4a0] bg-[#1b3528] text-[#7fd4a0]'
                : 'border-[#2a2f39] text-[#c8ccd4] hover:bg-[#1b1f27]',
            ].join(' ')}
          >
            {d}
          </button>
        );
      })}
    </fieldset>
  );
}
