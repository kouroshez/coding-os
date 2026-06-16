---
id: TASK-437
title: "Hub home: true cross-project Live-agents roster (registry walk + per-project DB scoping)"
swimlane: infra
kind: feature
epic: null
labels: [hub, presence, cross-project, scope-isolation, ready]
status: testing
priority: P2
appetite: 1d
created: 2026-06-16
started: 2026-06-16
completed: null
agent_session: ses-803-0b9f
depends_on: [TASK-435]
blocked_by: []
references: []
---
# TASK-437: Hub home: true cross-project Live-agents roster (registry walk + per-project DB scoping)

**Outcome (one sentence):** The Hub home "Live agents" panel shows agents across ALL registered projects (not just the Hub's launch-cwd project), each tagged with its owning project, so the all-projects dashboard is a genuine cross-project HUD. Today /api/presence/agents is single-project (current_project_root → cwd) and TASK-435 only stamps that one project's slug. This task makes the home view iterate cli.registry, scope each project's state dir + DB safely, and emit per-project agent groups — without leaking one project's DB handle into another (the exact hazard TASK-424 hardens).

## Read First
- docs/engineering/hub-architecture.md
- src/core/web/routes/presence.py
- src/core/web/_project_context.py
- src/cli/registry.py
- docs/tasks/TASK-435-fix-hub-home-live-agents-scope-loss-open-chat-projectswitche.md
- docs/tasks/TASK-424-cleanup-tail-hub-chat-in-process-presence-scope-leak-dedup-p.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** several registered projects each with a live agent, **When** I open the Hub home, **Then** the Live-agents panel lists agents from every project, each labelled with its project slug.
- **Given** a cross-project agent card, **When** I click Open chat, **Then** it opens /p/<that-project-slug>/cognition/<uuid> (reusing TASK-435's cognitionHref).
- **Given** the registry walk reads multiple projects' DBs, **When** presence is computed, **Then** no project's sqlite handle/state leaks into another (per-project keying per hub-architecture.md § Per-project backend keying); add a regression test.
- **Given** the change, **When** verified, **Then** presence pytest + a new cross-project test are green and the existing single-project /agents contract is unchanged.

## Notes
Depends on TASK-435 (slug stamping + cognitionHref already landed). The home panel may need a dedicated hub-level endpoint (e.g. /api/hub/agents) rather than overloading the per-project /api/presence/agents, to keep the single-project contract intact. Decide endpoint shape during design.

## Work Log
- 2026-06-16 [claude]: Edit presence.py
- 2026-06-16 [claude]: Edit hub.py
- 2026-06-16 [claude]: Edit test_hub_agents_cross_project.py
- 2026-06-16 [ses-803-0b9f]: Backend done: GET /api/hub/agents (hub.py) + cross_project_agents() (presence.py) walks cli.registry, scopes each projec
- 2026-06-16 [claude]: committed 79400c08 · 3 files
- 2026-06-16 [claude]: Edit presence.ts
- 2026-06-16 [claude]: Edit LiveAgentsPanel.tsx
- 2026-06-16 [claude]: Edit LiveAgentsPanel.tsx
- 2026-06-16 [claude]: Edit LiveAgentsPanel.tsx
- 2026-06-16 [claude]: Edit LiveAgentsPanel.tsx
- 2026-06-16 [claude]: Edit LiveAgentsPanel.tsx
- 2026-06-16 [claude]: Edit LiveAgentsPanel.test.tsx
- 2026-06-16 [ses-803-0b9f]: Frontend done: LiveAgentsPanel now consumes GET /api/hub/agents, flattens per-project groups into the landing grid, each
