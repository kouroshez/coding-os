import { Route, Routes, Navigate } from 'react-router-dom';
import { BoardThemeProvider } from '@/features/cos-board/BoardThemeProvider';
import AppShell from '@/layout/AppShell';
import { ErrorBoundary } from '@/layout/ErrorBoundary';
import CosBoardPage from '@/features/cos-board/CosBoardPage';
import GraphPage from './pages/GraphPage';
import MemoryPage from './pages/MemoryPage';
import HubHome from './pages/HubHome';
import DashboardPage from './pages/DashboardPage';
import ChatLanding from './pages/ChatLanding';
import ConfigPage from './pages/ConfigPage';
import ObservabilityPage from './pages/ObservabilityPage';
import LogsPage from './pages/LogsPage';
import SessionsPage from './pages/SessionsPage';
import DoctorPage from './pages/DoctorPage';
import NeedProjectPage from './pages/NeedProjectPage';
import WorkspacePage from './pages/WorkspacePage';
import DiagnosticsPage from './pages/DiagnosticsPage';
import {
  RedirectToConfigSettings,
  RedirectToDiagnostics,
  RedirectToWorkspace,
} from '@/lib/route-redirects';

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
            {/* Mission-control dashboard — moved home from Diagnostics (TASK-868). */}
            <Route path="overview" element={<DashboardPage />} />
            <Route path="chat" element={<NeedProjectPage feature="chat" />} />
            <Route path="board" element={<NeedProjectPage feature="board" />} />
            <Route path="memory" element={<NeedProjectPage feature="memory" />} />
          </Route>

          {/* Unified Diagnostics Hub (Global) */}
          <Route path="/diagnostics" element={<DiagnosticsPage />}>
            <Route index element={<Navigate to="doctor" replace />} />
            <Route path="overview" element={<Navigate to="/workspace/overview" replace />} />
            <Route path="doctor" element={<DoctorPage />} />
            <Route path="logs" element={<LogsPage />} />
            <Route path="observability" element={<ObservabilityPage />} />
            <Route path="sessions" element={<SessionsPage />} />
            <Route path="settings" element={<RedirectToConfigSettings />} />
          </Route>

          {/* Legacy & flat unscoped route redirects */}
          <Route path="/dashboard" element={<RedirectToWorkspace sub="overview" />} />
          <Route path="/board" element={<RedirectToWorkspace sub="board" />} />
          <Route path="/doctor" element={<RedirectToDiagnostics sub="doctor" />} />
          <Route path="/sessions" element={<RedirectToDiagnostics sub="sessions" />} />
          <Route path="/observability" element={<RedirectToDiagnostics sub="observability" />} />
          <Route path="/logs" element={<RedirectToDiagnostics sub="logs" />} />
          <Route path="/settings" element={<RedirectToConfigSettings />} />

          {/* Project-scoped features */}
          <Route path="/p/:slug/graph" element={<GraphPage />} />
          <Route path="/p/:slug/graph/:rootUid" element={<GraphPage />} />
          {/* Cognition was removed (TASK-1079); old session links open the chat. */}
          <Route path="/p/:slug/cognition" element={<RedirectToWorkspace sub="chat" />} />
          <Route path="/p/:slug/cognition/:sessionId" element={<RedirectToWorkspace sub="chat" />} />
          <Route path="/p/:slug/config" element={<ConfigPage />} />

          {/* Unified Workspace Hub (Project-Scoped) — chat-first landing */}
          <Route path="/p/:slug/workspace" element={<WorkspacePage />}>
            <Route index element={<Navigate to="chat" replace />} />
            {/* Mission-control dashboard — moved home from Diagnostics (TASK-868). */}
            <Route path="overview" element={<DashboardPage />} />
            <Route path="chat" element={<ChatLanding />} />
            <Route path="chat/:sessionId" element={<ChatLanding />} />
            <Route path="board" element={<CosBoardPage />} />
            <Route path="memory" element={<MemoryPage />} />
          </Route>

          {/* Unified Diagnostics Hub (Project-Scoped) */}
          <Route path="/p/:slug/diagnostics" element={<DiagnosticsPage />}>
            <Route index element={<Navigate to="doctor" replace />} />
            <Route path="overview" element={<RedirectToWorkspace sub="overview" />} />
            <Route path="doctor" element={<DoctorPage />} />
            <Route path="logs" element={<LogsPage />} />
            <Route path="observability" element={<ObservabilityPage />} />
            <Route path="sessions" element={<SessionsPage />} />
            <Route path="settings" element={<RedirectToConfigSettings />} />
          </Route>

          {/* Redirect old flat project routes to nested hubs */}
          <Route path="/p/:slug" element={<RedirectToWorkspace sub="chat" />} />
          <Route path="/p/:slug/dashboard" element={<RedirectToWorkspace sub="overview" />} />
          <Route path="/p/:slug/board" element={<RedirectToWorkspace sub="board" />} />
          <Route path="/p/:slug/memory" element={<RedirectToWorkspace sub="memory" />} />
          {/* chat/overview were missing here, so a flat link to
              them matched nothing and the `*` catch-all bounced the user to Hub
              home. Every WORKSPACE_TABS entry needs a flat form. */}
          <Route path="/p/:slug/chat" element={<RedirectToWorkspace sub="chat" />} />
          <Route path="/p/:slug/chat/:sessionId" element={<RedirectToWorkspace sub="chat" />} />
          <Route path="/p/:slug/overview" element={<RedirectToWorkspace sub="overview" />} />
          <Route path="/p/:slug/doctor" element={<RedirectToDiagnostics sub="doctor" />} />
          <Route path="/p/:slug/logs" element={<RedirectToDiagnostics sub="logs" />} />
          <Route path="/p/:slug/observability" element={<RedirectToDiagnostics sub="observability" />} />
          <Route path="/p/:slug/sessions" element={<RedirectToDiagnostics sub="sessions" />} />

          {/* Fallback */}
          <Route path="/graph" element={<NeedProjectPage feature="graph" />} />
          <Route path="/graph/:rootUid" element={<NeedProjectPage feature="graph" />} />
          <Route path="/cognition" element={<NeedProjectPage feature="chat" />} />
          <Route path="/cognition/:sessionId" element={<NeedProjectPage feature="chat" />} />
          <Route path="/config" element={<NeedProjectPage feature="config" />} />
          <Route path="/roles" element={<Navigate to="/" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BoardThemeProvider>
    </ErrorBoundary>
  );
}
