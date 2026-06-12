import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { PanelLeftOpen, SlidersHorizontal, X } from 'lucide-react';
import { useGraphStore } from '@/store/graph-store';
import ContainsTree from '@/features/graph/ContainsTree';
import GraphCanvas from '@/features/graph/GraphCanvas';
import FilterBar from '@/features/graph/filter-bar';
import DepthSlider from '@/features/graph/depth-slider';
import ColorLegend from '@/features/graph/color-legend';
import ViewModeTabs from '@/features/graph/view-mode-tabs';

// Graph page: tree (left, fixed) + canvas (center, flex) + floating
// widgets (top-right overlay + bottom-right legend). Inspector lives
// in the app shell and listens to selectedNodeUid via zustand.
export default function GraphPage() {
  const { rootUid } = useParams<{ rootUid?: string }>();
  const setRoot = useGraphStore((s) => s.setRoot);
  const spineOpen = useGraphStore((s) => s.spineOpen);
  const toggleSpine = useGraphStore((s) => s.toggleSpine);
  const filtersOpen = useGraphStore((s) => s.filtersOpen);
  const toggleFilters = useGraphStore((s) => s.toggleFilters);

  // URL is the single source of truth; mutators (ContainsTree row
  // click, Clear button, ProjectSwitcher) call useNavigate themselves
  // so we only sync URL -> store here. The previous bidirectional
  // pair of effects produced a render loop after the edge-field bug
  // was fixed.
  useEffect(() => {
    setRoot(rootUid ?? null);
  }, [rootUid, setRoot]);

  return (
    <div
      className="grid h-full w-full"
      style={{ gridTemplateColumns: spineOpen ? '260px 1fr' : '28px 1fr' }}
    >
      {spineOpen ? (
        <aside className="border-r border-[var(--cos-border)] bg-[var(--cos-panel)]">
          <ContainsTree />
        </aside>
      ) : (
        <button
          type="button"
          onClick={toggleSpine}
          title="Show Contains spine"
          aria-label="Show Contains spine"
          className="flex items-start justify-center border-r border-[var(--cos-border)] bg-[var(--cos-panel)] pt-3 text-[var(--cos-muted)] hover:text-[var(--cos-text)] focus-visible:ring-2"
        >
          <PanelLeftOpen size={14} aria-hidden />
        </button>
      )}
      <section className="relative overflow-hidden">
        <div className="absolute left-1/2 top-3 z-10 -translate-x-1/2 rounded-full border border-white/10 bg-[var(--cos-panel)]/70 shadow-xl backdrop-blur-md">
          <ViewModeTabs />
        </div>
        <div className="absolute left-3 top-3 z-10 flex flex-col gap-2 rounded-xl border border-white/10 bg-[var(--cos-panel)]/70 p-3 shadow-xl backdrop-blur-md">
          <DepthSlider />
        </div>
        {filtersOpen ? (
          <div className="absolute right-3 top-3 z-10 w-64 rounded-xl border border-white/10 bg-[var(--cos-panel)]/70 p-3 shadow-xl backdrop-blur-md transition-colors hover:bg-[var(--cos-panel)]/80">
            <button
              type="button"
              onClick={toggleFilters}
              title="Hide search & filters"
              aria-label="Hide search & filters"
              className="absolute right-2 top-2 text-[var(--cos-muted)] hover:text-[var(--cos-text)] focus-visible:ring-2"
            >
              <X size={12} aria-hidden />
            </button>
            <FilterBar />
          </div>
        ) : (
          <button
            type="button"
            onClick={toggleFilters}
            title="Show search & filters"
            aria-label="Show search & filters"
            className="absolute right-3 top-3 z-10 rounded-xl border border-white/10 bg-[var(--cos-panel)]/70 p-2 text-[var(--cos-muted)] shadow-xl backdrop-blur-md hover:text-[var(--cos-text)] focus-visible:ring-2"
          >
            <SlidersHorizontal size={14} aria-hidden />
          </button>
        )}
        <div className="absolute bottom-3 right-3 z-10 w-48 rounded-xl border border-white/10 bg-[var(--cos-panel)]/70 shadow-xl backdrop-blur-md transition-colors hover:bg-[var(--cos-panel)]/80">
          <ColorLegend />
        </div>
        <GraphCanvas />
      </section>
    </div>
  );
}
