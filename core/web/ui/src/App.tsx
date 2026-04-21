import { Route, Routes, Navigate } from 'react-router-dom';
import Header from './layout/Header';
import Sidebar from './layout/Sidebar';
import Inspector from './layout/Inspector';
import GraphPage from './pages/GraphPage';
import BoardPage from './pages/BoardPage';
import CognitionPage from './pages/CognitionPage';
import SearchPage from './pages/SearchPage';

// Root layout: 3-column grid (sidebar / main / inspector).
// Inspector visibility is route-decided; shell keeps it always mounted so
// per-page state survives URL transitions.
export default function App() {
  return (
    <div
      className="grid h-screen w-screen overflow-hidden"
      style={{ gridTemplateColumns: '200px 1fr 320px', gridTemplateRows: '48px 1fr' }}
    >
      <div className="col-span-3 row-span-1">
        <Header />
      </div>
      <aside className="row-span-1 border-r border-[#2a2f39] bg-[#151a22]">
        <Sidebar />
      </aside>
      <main className="row-span-1 overflow-hidden bg-[#11151c]">
        <Routes>
          <Route path="/" element={<Navigate to="/graph" replace />} />
          <Route path="/graph" element={<GraphPage />} />
          <Route path="/graph/:rootUid" element={<GraphPage />} />
          <Route path="/board" element={<BoardPage />} />
          <Route path="/cognition" element={<CognitionPage />} />
          <Route path="/cognition/:sessionId" element={<CognitionPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="*" element={<Navigate to="/graph" replace />} />
        </Routes>
      </main>
      <aside className="row-span-1 border-l border-[#2a2f39] bg-[#151a22]">
        <Inspector />
      </aside>
    </div>
  );
}
