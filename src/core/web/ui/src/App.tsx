import { Route, Routes, Navigate, useParams } from 'react-router-dom';
import { BoardThemeProvider } from '@/features/cos-board/BoardThemeProvider';
import AppShell from '@/layout/AppShell';
import { ErrorBoundary } from '@/layout/ErrorBoundary';
import CosBoardPage from '@/features/cos-board/CosBoardPage';
import GraphPage from './pages/GraphPage';
import CognitionPage from './pages/CognitionPage';
import SearchPage from './pages/SearchPage';
import HubHome from './pages/HubHome';
import DashboardPage from './pages/DashboardPage';
import ChatLanding from './pages/ChatLanding';
import ConfigPage from './pages/ConfigPage';
import SettingsPage from './pages/SettingsPage';
import ObservabilityPage from './pages/ObservabilityPage';
import LogsPage from './pages/LogsPage';
import SessionsPage from './pages/SessionsPage';
import DoctorPage from './pages/DoctorPage';
import AuditsPage from './pages/AuditsPage';
import MemoryPage from './pages/MemoryPage';
import NeedProjectPage from './pages/NeedProjectPage';
import WorkspacePage from './pages/WorkspacePage';
import DiagnosticsPage from './pages/DiagnosticsPage';

// Redirect helpers to transition old deep-links smoothly to nested hub routes
function RedirectToWorkspace({ sub }: { sub: string }) {
  const { slug } = useParams<{ slug?: string }>();
  return <Navigate to={slug ? `/p/${encodeURIComponent(slug)}/workspace/${sub}` : `/workspace/${sub}`} replace />;
}

function RedirectToDiagnostics({ sub }: { sub: string }) {
  const { slug } = useParams<{ slug?: string }>();
  return <Navigate to={slug ? `/p/${encodeURIComponent(slug)}/diagnostics/${sub}` : `/diagnostics/${sub}`} replace />;
}

export default function App() {
  return (
    <ErrorBoundary>
    <BoardThemeProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<HubHome />} />

          {/* Unified Workspace Hub (Global / Unscoped) */}
          <Route path="/workspace" element={<WorkspacePage />}>
            <Route index element={<Navigate to="chat" replace />} />
            <Route path="chat" element={<NeedProjectPage feature="chat" />} />
            <Route path="board" element={<NeedProjectPage feature="board" />} />
            <Route path="search" element={<NeedProjectPage feature="search" />} />
          </Route>

          {/* Unified Diagnostics Hub (Global) */}
          <Route path="/diagnostics" element={<DiagnosticsPage />}>
            <Route index element={<Navigate to="overview" replace />} />
            {/* DashboardPage now serves the Diagnostics Overview (TASK-250). */}
            <Route path="overview" element={<DashboardPage />} />
            <Route path="doctor" element={<DoctorPage />} />
            <Route path="logs" element={<LogsPage />} />
            <Route path="observability" element={<ObservabilityPage />} />
            <Route path="sessions" element={<SessionsPage />} />
            <Route path="audits" element={<AuditsPage />} />
            <Route path="memory" element={<MemoryPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>

          {/* Legacy & flat unscoped route redirects */}
          <Route path="/dashboard" element={<RedirectToDiagnostics sub="overview" />} />
          <Route path="/board" element={<RedirectToWorkspace sub="board" />} />
          <Route path="/search" element={<RedirectToWorkspace sub="search" />} />
          <Route path="/doctor" element={<RedirectToDiagnostics sub="doctor" />} />
          <Route path="/sessions" element={<RedirectToDiagnostics sub="sessions" />} />
          <Route path="/observability" element={<RedirectToDiagnostics sub="observability" />} />
          <Route path="/logs" element={<RedirectToDiagnostics sub="logs" />} />
          <Route path="/settings" element={<RedirectToDiagnostics sub="settings" />} />
          <Route path="/audits" element={<RedirectToDiagnostics sub="audits" />} />

          {/* Project-scoped features */}
          <Route path="/p/:slug/graph" element={<GraphPage />} />
          <Route path="/p/:slug/graph/:rootUid" element={<GraphPage />} />
          <Route path="/p/:slug/cognition" element={<CognitionPage />} />
          <Route path="/p/:slug/cognition/:sessionId" element={<CognitionPage />} />
          <Route path="/p/:slug/config" element={<ConfigPage />} />

          {/* Unified Workspace Hub (Project-Scoped) — chat-first landing */}
          <Route path="/p/:slug/workspace" element={<WorkspacePage />}>
            <Route index element={<Navigate to="chat" replace />} />
            <Route path="chat" element={<ChatLanding />} />
            <Route path="chat/:sessionId" element={<ChatLanding />} />
            <Route path="board" element={<CosBoardPage />} />
            <Route path="search" element={<SearchPage />} />
          </Route>

          {/* Unified Diagnostics Hub (Project-Scoped) */}
          <Route path="/p/:slug/diagnostics" element={<DiagnosticsPage />}>
            <Route index element={<Navigate to="overview" replace />} />
            {/* Re-homed dashboard telemetry widgets (TASK-250). */}
            <Route path="overview" element={<DashboardPage />} />
            <Route path="doctor" element={<DoctorPage />} />
            <Route path="logs" element={<LogsPage />} />
            <Route path="observability" element={<ObservabilityPage />} />
            <Route path="sessions" element={<SessionsPage />} />
            <Route path="audits" element={<AuditsPage />} />
            <Route path="memory" element={<MemoryPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>

          {/* Redirect old flat project routes to nested hubs */}
          <Route path="/p/:slug" element={<RedirectToWorkspace sub="chat" />} />
          <Route path="/p/:slug/dashboard" element={<RedirectToDiagnostics sub="overview" />} />
          <Route path="/p/:slug/board" element={<RedirectToWorkspace sub="board" />} />
          <Route path="/p/:slug/search" element={<RedirectToWorkspace sub="search" />} />
          <Route path="/p/:slug/doctor" element={<RedirectToDiagnostics sub="doctor" />} />
          <Route path="/p/:slug/logs" element={<RedirectToDiagnostics sub="logs" />} />
          <Route path="/p/:slug/observability" element={<RedirectToDiagnostics sub="observability" />} />
          <Route path="/p/:slug/sessions" element={<RedirectToDiagnostics sub="sessions" />} />
          <Route path="/p/:slug/audits" element={<RedirectToDiagnostics sub="audits" />} />

          {/* Fallback */}
          <Route path="/graph" element={<NeedProjectPage feature="graph" />} />
          <Route path="/graph/:rootUid" element={<NeedProjectPage feature="graph" />} />
          <Route path="/cognition" element={<NeedProjectPage feature="cognition" />} />
          <Route path="/cognition/:sessionId" element={<NeedProjectPage feature="cognition" />} />
          <Route path="/config" element={<NeedProjectPage feature="config" />} />
          <Route path="/roles" element={<Navigate to="/" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BoardThemeProvider>
    </ErrorBoundary>
  );
}
