import { useRef, type KeyboardEvent } from 'react';
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
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  // WAI-ARIA tabs keyboard model: Arrow/Home/End move focus + selection across
  // the tablist (roving tabindex means only the active tab is in the Tab order).
  const onTabKeyDown = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = TABS.length - 1;
    let next = index;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = index === last ? 0 : index + 1;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = index === 0 ? last : index - 1;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = last;
    else return;
    e.preventDefault();
    setViewMode(TABS[next].value);
    tabRefs.current[next]?.focus();
  };

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
            onKeyDown={(e) => onTabKeyDown(e, i)}
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
