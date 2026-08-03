import { useRovingTabList } from '@/lib/use-roving-tablist';
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
    label: 'Communities',
    hint: 'Louvain community detection — one header node per subsystem + its top member hubs',
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
  const { tabRefs, onKeyDown } = useRovingTabList(TABS.length, (i) => setViewMode(TABS[i].value));

  return (
    <div
      role="tablist"
      aria-label="Graph view mode"
      className="flex items-center gap-1 p-1 text-xs"
    >
      {TABS.map((t, i) => {
        const active = viewMode === t.value;
        return (
          <button
            key={t.value}
            ref={(el) => {
              tabRefs.current[i] = el;
            }}
            role="tab"
            type="button"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            title={t.hint}
            onClick={() => setViewMode(t.value)}
            onKeyDown={(e) => onKeyDown(e, i)}
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
