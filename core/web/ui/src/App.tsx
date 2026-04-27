import { Route, Routes, Navigate } from 'react-router-dom';
import { BoardThemeProvider } from '@/features/cos-board/BoardThemeProvider';
import AppShell from '@/layout/AppShell';
import { ErrorBoundary } from '@/layout/ErrorBoundary';
import CosBoardPage from '@/features/cos-board/CosBoardPage';
import GraphPage from './pages/GraphPage';
import CognitionPage from './pages/CognitionPage';
import SearchPage from './pages/SearchPage';
import HubHome from './pages/HubHome';

export default function App() {
  return (
    <ErrorBoundary>
    <BoardThemeProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<HubHome />} />
          <Route path="/board" element={<CosBoardPage />} />
          <Route path="/graph" element={<GraphPage />} />
          <Route path="/graph/:rootUid" element={<GraphPage />} />
          <Route path="/cognition" element={<CognitionPage />} />
          <Route path="/cognition/:sessionId" element={<CognitionPage />} />
          <Route path="/search" element={<SearchPage />} />
          {/*
            Per-project deep links.  The backend middleware rewrites
            /api/p/<slug>/... → /api/... and scopes the project for the
            request.  On the SPA side we just reuse the same feature
            components — React Router passes the `slug` param down and
            api-client helpers pick it up to rewrite fetches to the
            per-project endpoint.
          */}
          <Route path="/p/:slug/board" element={<CosBoardPage />} />
          <Route path="/p/:slug/graph" element={<GraphPage />} />
          <Route path="/p/:slug/graph/:rootUid" element={<GraphPage />} />
          <Route path="/p/:slug/search" element={<SearchPage />} />
          <Route path="/p/:slug/cognition" element={<CognitionPage />} />
          <Route path="/p/:slug/cognition/:sessionId" element={<CognitionPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BoardThemeProvider>
    </ErrorBoundary>
  );
}
