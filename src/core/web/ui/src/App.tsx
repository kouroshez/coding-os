import { Route, Routes, Navigate } from 'react-router-dom';
import { BoardThemeProvider } from '@/features/cos-board/BoardThemeProvider';
import AppShell from '@/layout/AppShell';
import { ErrorBoundary } from '@/layout/ErrorBoundary';
import CosBoardPage from '@/features/cos-board/CosBoardPage';
import GraphPage from './pages/GraphPage';
import CognitionPage from './pages/CognitionPage';
import SearchPage from './pages/SearchPage';
import HubHome from './pages/HubHome';
import DashboardPage from './pages/DashboardPage';
import SettingsPage from './pages/SettingsPage';
import ObservabilityPage from './pages/ObservabilityPage';
import LogsPage from './pages/LogsPage';
import SessionsPage from './pages/SessionsPage';
import DoctorPage from './pages/DoctorPage';

export default function App() {
  return (
    <ErrorBoundary>
    <BoardThemeProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<HubHome />} />
          {/*
            Hub-level features — always reachable without a project
            slug.  Their data is global to the hub itself (server
            health, agent presence across all projects, hook event
            stream, hub config).  Per-project deep-links to the same
            pages are still available under /p/<slug>/ for convenience.
          */}
          <Route path="/doctor" element={<DoctorPage />} />
          <Route path="/sessions" element={<SessionsPage />} />
          <Route path="/observability" element={<ObservabilityPage />} />
          <Route path="/logs" element={<LogsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          {/*
            Project-scoped features REQUIRE a /p/<slug>/ prefix.  The
            slug-less variants redirect to the Hub home (project
            picker) so users explicitly select a project before
            opening any project-specific panel.
          */}
          <Route path="/dashboard" element={<Navigate to="/" replace />} />
          <Route path="/board" element={<Navigate to="/" replace />} />
          <Route path="/graph" element={<Navigate to="/" replace />} />
          <Route path="/graph/:rootUid" element={<Navigate to="/" replace />} />
          <Route path="/cognition" element={<Navigate to="/" replace />} />
          <Route path="/cognition/:sessionId" element={<Navigate to="/" replace />} />
          <Route path="/search" element={<Navigate to="/" replace />} />
          {/* Legacy redirect kept for old bookmarks pointing to /roles. */}
          <Route path="/roles" element={<Navigate to="/" replace />} />
          {/*
            Per-project deep links.  The backend middleware rewrites
            /api/p/<slug>/... → /api/... and scopes the project for the
            request.  On the SPA side we just reuse the same feature
            components — React Router passes the `slug` param down and
            api-client helpers pick it up to rewrite fetches to the
            per-project endpoint.
          */}
          <Route path="/p/:slug" element={<DashboardPage />} />
          <Route path="/p/:slug/dashboard" element={<DashboardPage />} />
          <Route path="/p/:slug/board" element={<CosBoardPage />} />
          <Route path="/p/:slug/graph" element={<GraphPage />} />
          <Route path="/p/:slug/graph/:rootUid" element={<GraphPage />} />
          <Route path="/p/:slug/search" element={<SearchPage />} />
          <Route path="/p/:slug/cognition" element={<CognitionPage />} />
          <Route path="/p/:slug/cognition/:sessionId" element={<CognitionPage />} />
          <Route path="/p/:slug/observability" element={<ObservabilityPage />} />
          <Route path="/p/:slug/logs" element={<LogsPage />} />
          <Route path="/p/:slug/sessions" element={<SessionsPage />} />
          <Route path="/p/:slug/doctor" element={<DoctorPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BoardThemeProvider>
    </ErrorBoundary>
  );
}
