---
id: TASK-435
title: "Fix Hub home Live-agents scope-loss (Open chat / ProjectSwitcher / NeedProjectPage) + redesign HubHome landing UX"
swimlane: infra
kind: feature
epic: null
labels: [hub, ui, presence, scope-loss, ux, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-16
started: 2026-06-15
completed: 2026-06-16
agent_session: ses-claude-20260615-232816-54b1
depends_on: []
blocked_by: []
references: []
---
# TASK-435: Fix Hub home Live-agents scope-loss (Open chat / ProjectSwitcher / NeedProjectPage) + redesign HubHome landing UX

**Outcome (one sentence):** The Hub home page (/) is a coherent project launcher AND every live-agent "Open chat" opens the agent's real project-scoped transcript instead of dead-ending at the project picker. Root cause: the /api/presence/agents payload carries no owning-project slug, so useScopedLink degrades to an unscoped /cognition link → NeedProjectPage (violates TASK-194 DoD + agent-hub-orchestration.md T14/T17). Fix = stamp slug onto presence + build explicit scoped links; plus repair two sibling scope-loss bugs (ProjectSwitcher reset-to-Board, NeedProjectPage drops sessionId); plus redesign HubHome into a clean launcher reusing HubPrimitives.

## Read First
- docs/engineering/hub-architecture.md
- docs/engineering/agent-hub-orchestration.md
- src/core/web/ui/src/pages/HubHome.tsx
- src/core/web/routes/presence.py
- src/core/web/ui/src/lib/use-scoped-link.ts
- src/core/web/ui/src/layout/ProjectSwitcher.tsx

## Repro
Open http://127.0.0.1:9188/ → "Live agents" → click "Open chat →" on an agent card → lands on "Pick a project to open Cognition" (NeedProjectPage) instead of the agent's chat. Also: switch project from /p/foo/diagnostics/logs via the header ProjectSwitcher → jumps to /p/bar/board (loses Diagnostics + Logs).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Hub home page with a live agent, **When** I click "Open chat", **Then** it opens that agent's project-scoped chat (/p/<slug>/cognition/<uuid>?view=chat), never the NeedProjectPage picker.
- **Given** a project-scoped workspace/diagnostics/config sub-tab, **When** I switch project via the header ProjectSwitcher, **Then** I stay on the same feature + sub-tab under the new slug (not reset to Board).
- **Given** NeedProjectPage reached with a :sessionId in the URL, **When** I pick a project, **Then** I land on that feature WITH the sessionId preserved.
- **Given** the redesigned HubHome, **When** it renders, **Then** each project tile opens the project on click, Chat is reachable from the tile, Prune requires dry-run + confirm, and HubHome imports ActionPill/Banner/SkeletonGrid from HubPrimitives (no local dupes, no ToolbarButton variant).
- **Given** the UI + backend changes, **When** verified, **Then** vitest is green, `make ui-build` succeeds, and presence pytest is green.

## Follow-up (out of scope — file separately)
True cross-project Live-agents roster: iterate `cli.registry` projects, scope each project's state dir + DB, and stamp each agent with its source slug so the home HUD shows agents across ALL projects (not just the Hub's launch-cwd). Needs per-project DB scoping — the area TASK-424 is hardening; do NOT rush it into this task.

## Work Log
- 2026-06-16 [claude]: Edit hub-architecture.md
- 2026-06-16 [claude]: Edit presence.py
- 2026-06-16 [claude]: Edit presence.py
- 2026-06-16 [claude]: Edit presence.py
- 2026-06-16 [claude]: Edit presence.ts
- 2026-06-16 [claude]: Edit presence.ts
- 2026-06-16 [claude]: Edit LiveAgentsPanel.tsx
- 2026-06-16 [claude]: Edit LiveAgentsPanel.tsx
- 2026-06-16 [claude]: Edit AgentDetailModal.tsx
- 2026-06-16 [claude]: Edit AgentDetailModal.tsx
- 2026-06-16 [claude]: Edit presence.py
- 2026-06-16 [claude]: Edit presence.py
- 2026-06-16 [claude]: Edit LiveStatus.tsx
- 2026-06-16 [claude]: Edit LiveStatus.tsx
- 2026-06-16 [claude]: Edit LiveStatus.tsx
- 2026-06-16 [claude]: Edit LiveStatus.tsx
- 2026-06-16 [claude]: Edit LiveStatus.tsx
- 2026-06-16 [claude]: Edit ProjectSwitcher.tsx
- 2026-06-16 [claude]: Edit ProjectSwitcher.tsx
- 2026-06-16 [claude]: Edit ProjectSwitcher.tsx
- 2026-06-16 [claude]: Edit NeedProjectPage.tsx
- 2026-06-16 [claude]: Edit NeedProjectPage.tsx
- 2026-06-16 [claude]: Edit HubHome.tsx
- 2026-06-16 [claude]: Edit HubHome.tsx
- 2026-06-16 [claude]: Edit HubHome.tsx
- 2026-06-16 [claude]: Edit HubHome.tsx
- 2026-06-16 [claude]: Edit HubHome.tsx
- 2026-06-16 [claude]: Edit HubHome.tsx
- 2026-06-16 [claude]: Edit HubHome.tsx
- 2026-06-16 [claude]: Edit HubHome.tsx
- 2026-06-16 [claude]: Edit HubHome.tsx
- 2026-06-16 [claude]: Edit HubHome.tsx
- 2026-06-16 [claude]: Edit HubHome.tsx
- 2026-06-16 [claude]: Edit presence.test.ts
- 2026-06-16 [claude]: Edit presence.test.ts
- 2026-06-16 [claude]: Edit test_presence_agents_route.py
- 2026-06-16 [claude]: Landed: presence.py stamps owning-project slug on /agents+/now (new _project_slug); presence.ts adds slug + pure cogniti
- 2026-06-16 [claude]: committed 252fd742 · 11 files
- 2026-06-16 [claude]: Status transitioned to complete via cos task-done.
