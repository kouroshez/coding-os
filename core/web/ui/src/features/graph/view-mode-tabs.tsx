import { useGraphStore, type ViewMode } from '@/store/graph-store';

const TABS: ReadonlyArray<{ value: ViewMode; label: string; hint: string }> = [
  {
    value: 'auto',
    label: 'Auto',
    hint: 'Balanced blend of containment + dependencies',
  },
  {
    value: 'containment',
    label: 'Containment',
    hint: 'Folder → file → class → method (dagre tree)',
  },
  {
    value: 'dependencies',
    label: 'Dependencies',
    hint: 'imports / calls / inherits / handles_*',
  },
  {
    value: 'processes',
    label: 'Processes',
    hint: 'Louvain communities (TASK-075)',
  },
];

/**
 * Top-of-canvas view-mode selector — TASK-141 P2.
 *
 * Each tab swaps the `mode` query param sent to /api/graph/export, which
 * the backend uses to compose a different blend of edges (see
 * `_AUTO_BLEND_BUCKETS` in graph_os/tools/graph.py).  Tabs are radio-
 * styled so only one can be active; the active mode is highlighted
 * with the cos-accent colour.
 */
export default function ViewModeTabs() {
  const viewMode = useGraphStore((s) => s.viewMode);
  const setViewMode = useGraphStore((s) => s.setViewMode);

  return (
    <div
      role="tablist"
      aria-label="Graph view mode"
      className="flex items-center gap-1 rounded border border-[var(--cos-border)] bg-[var(--cos-panel)]/95 p-1 text-xs shadow-sm backdrop-blur"
    >
      {TABS.map((t) => {
        const active = viewMode === t.value;
        return (
          <button
            key={t.value}
            role="tab"
            type="button"
            aria-selected={active}
            title={t.hint}
            onClick={() => setViewMode(t.value)}
            className={[
              'rounded px-2 py-1 transition-colors',
              active
                ? 'bg-[var(--cos-accent)]/15 text-[var(--cos-accent)]'
                : 'text-[var(--cos-muted)] hover:bg-[var(--cos-panel)] hover:text-white',
            ].join(' ')}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
