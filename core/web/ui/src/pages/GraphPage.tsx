import { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useGraphStore } from '@/store/graph-store';
import ContainsTree from '@/features/graph/ContainsTree';
import GraphCanvas from '@/features/graph/GraphCanvas';
import FilterBar from '@/features/graph/filter-bar';
import DepthSlider from '@/features/graph/depth-slider';
import ColorLegend from '@/features/graph/color-legend';

// Graph page: tree (left, fixed) + canvas (center, flex) + floating
// widgets (top-right overlay + bottom-right legend). Inspector lives
// in the app shell and listens to selectedNodeUid via zustand.
export default function GraphPage() {
  const { rootUid } = useParams<{ rootUid?: string }>();
  const navigate = useNavigate();
  const selectedRootUid = useGraphStore((s) => s.selectedRootUid);
  const setRoot = useGraphStore((s) => s.setRoot);

  // URL <-> store sync: /graph/:rootUid? is the canonical pointer.
  useEffect(() => {
    if (rootUid && rootUid !== selectedRootUid) setRoot(rootUid);
    if (!rootUid && selectedRootUid) setRoot(null);
  }, [rootUid, selectedRootUid, setRoot]);

  useEffect(() => {
    if (selectedRootUid && selectedRootUid !== rootUid) {
      navigate(`/graph/${encodeURIComponent(selectedRootUid)}`, { replace: true });
    }
    if (!selectedRootUid && rootUid) {
      navigate('/graph', { replace: true });
    }
  }, [selectedRootUid, rootUid, navigate]);

  return (
    <div
      className="grid h-full w-full"
      style={{ gridTemplateColumns: '260px 1fr' }}
    >
      <aside className="border-r border-[var(--cos-border)] bg-[var(--cos-panel)]">
        <ContainsTree />
      </aside>
      <section className="relative overflow-hidden">
        <div className="absolute left-3 top-3 z-10 flex flex-col gap-2">
          <DepthSlider />
        </div>
        <div className="absolute right-3 top-3 z-10 w-64 rounded border border-[var(--cos-border)] bg-[var(--cos-panel)]/95 p-2 shadow-lg backdrop-blur">
          <FilterBar />
        </div>
        <div className="absolute bottom-3 right-3 z-10 w-48">
          <ColorLegend />
        </div>
        <GraphCanvas />
      </section>
    </div>
  );
}
