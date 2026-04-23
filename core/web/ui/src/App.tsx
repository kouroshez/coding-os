import { Route, Routes, Navigate } from 'react-router-dom';
import { BoardThemeProvider } from '@/features/cos-board/BoardThemeProvider';
import CosShellLayout from '@/features/cos-board/CosShellLayout';
import CosBoardPage from '@/features/cos-board/CosBoardPage';
import GraphPage from './pages/GraphPage';
import CognitionPage from './pages/CognitionPage';
import SearchPage from './pages/SearchPage';

export default function App() {
  return (
    <BoardThemeProvider>
      <Routes>
        <Route element={<CosShellLayout />}>
          <Route path="/" element={<Navigate to="/board" replace />} />
          <Route path="/board" element={<CosBoardPage />} />
          <Route path="/graph" element={<GraphPage />} />
          <Route path="/graph/:rootUid" element={<GraphPage />} />
          <Route path="/cognition" element={<CognitionPage />} />
          <Route path="/cognition/:sessionId" element={<CognitionPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="*" element={<Navigate to="/board" replace />} />
        </Route>
      </Routes>
    </BoardThemeProvider>
  );
}
