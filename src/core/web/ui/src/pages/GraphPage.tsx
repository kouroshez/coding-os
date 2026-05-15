import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
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

  // URL is the single source of truth; mutators (ContainsTree row
  // click, Clear button, ProjectSwitcher) call useNavigate themselves
  // so we only sync URL -> store here. The previous bidirectional
  // pair of effects produced a render loop after the edge-field bug
  // was fixed (per TASK-117).
  useEffect(() => {
    setRoot(rootUid ?? null);
  }, [rootUid, setRoot]);

  return (
    <div
      className="grid h-full w-full"
      style={{ gridTemplateColumns: '260px 1fr' }}
    >
      <aside className="border-r border-[var(--cos-border)] bg-[var(--cos-panel)]">
        <ContainsTree />
      </aside>
      <section className="relative overflow-hidden">
        <div className="absolute left-1/2 top-3 z-10 -translate-x-1/2 rounded-full border border-white/10 bg-[var(--cos-panel)]/70 shadow-xl backdrop-blur-md">
          <ViewModeTabs />
        </div>
        <div className="absolute left-3 top-3 z-10 flex flex-col gap-2 rounded-xl border border-white/10 bg-[var(--cos-panel)]/70 p-3 shadow-xl backdrop-blur-md">
          <DepthSlider />
        </div>
        <div className="absolute right-3 top-3 z-10 w-64 rounded-xl border border-white/10 bg-[var(--cos-panel)]/70 p-3 shadow-xl backdrop-blur-md transition-colors hover:bg-[var(--cos-panel)]/80">
          <FilterBar />
        </div>
        <div className="absolute bottom-3 right-3 z-10 w-48 rounded-xl border border-white/10 bg-[var(--cos-panel)]/70 shadow-xl backdrop-blur-md transition-colors hover:bg-[var(--cos-panel)]/80">
          <ColorLegend />
        </div>
        <GraphCanvas />
      </section>
    </div>
  );
}
