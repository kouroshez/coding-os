---
id: TASK-864
title: "Pre-release Hub UI audit: Playwright screen-by-screen cleanup and consolidation"
swimlane: core
kind: chore
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-03
started: 2026-08-03
completed: 2026-08-03
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-864: Pre-release Hub UI audit: Playwright screen-by-screen cleanup and consolidation

**Outcome (one sentence):** Every Hub screen is audited live via Playwright, redundant/broken tabs are removed or merged (Settings→Config, Diagnostics consolidated, Memory relocated), and all remaining functionality verified working — ready for public GitHub release.

## Read First

- docs/engineering/hub-architecture.md — Hub contract
- src/core/web/ui/src/ — SPA source (routes, pages, tabs)
- src/core/web/routes/ — FastAPI producers

## Acceptance (G/W/T)

- Given the Hub at :9188, when each nav screen and sub-tab is exercised via Playwright, then no dead/broken tab remains and each surviving screen's actions verifiably work end-to-end.
- Given Config screen, when a skill/plugin/module is toggled, then the change applies immediately and is reflected on re-load.
- Given Diagnostics, when reviewed, then its tabs are relocated/merged per audit decisions (Settings merged into Config; Memory placed with workspace tabs; doctor charts show real data only).
- Given the audit checklist, when complete, then every item has a verdict: keep / fix (fixed) / remove (removed) with evidence.

## Work Log
- 2026-08-03 [claude]: Playwright audit complete across all screens. Findings: (1) chat list shows formula-dispatch system sessions despite…
- 2026-08-03 [claude]: Deliberation: chose consolidation-over-deletion for working surfaces and deletion for dead ones — honors…
- 2026-08-03 [claude]: Edit hub-architecture.md
- 2026-08-03 [claude]: Edit pyproject.toml
- 2026-08-03 [claude]: Edit WorkspacePage.tsx
- 2026-08-03 [claude]: Edit WorkspacePage.tsx
- 2026-08-03 [claude]: Edit DiagnosticsPage.tsx
- 2026-08-03 [claude]: Edit DiagnosticsPage.tsx
- 2026-08-03 [claude]: Edit ConfigPage.tsx
- 2026-08-03 [claude]: Edit ConfigPage.tsx
- 2026-08-03 [claude]: Edit ConfigPage.tsx
- 2026-08-03 [claude]: Edit App.tsx
- 2026-08-03 [claude]: Edit App.tsx
- 2026-08-03 [claude]: Edit App.tsx
- 2026-08-03 [claude]: Edit App.tsx
- 2026-08-03 [claude]: Edit AppShell.tsx
- 2026-08-03 [claude]: Edit AppShell.tsx
- 2026-08-03 [claude]: commit 0c6e665636 — feat(hub): consolidate IA — Settings into Config, Memory into Workspace, slim Diagnostics
- 2026-08-03 [claude]: Edit ChatList.tsx
- 2026-08-03 [claude]: Edit attention.ts
- 2026-08-03 [claude]: Edit AttentionBell.tsx
- 2026-08-03 [claude]: Edit DoctorPage.tsx
- 2026-08-03 [claude]: Edit DoctorPage.tsx
- 2026-08-03 [claude]: Edit DoctorPage.tsx
- 2026-08-03 [claude]: Edit DoctorPage.tsx
- 2026-08-03 [claude]: Edit DoctorPage.tsx
- 2026-08-03 [claude]: Edit DoctorPage.tsx
- 2026-08-03 [claude]: Edit view-mode-tabs.tsx
- 2026-08-03 [claude]: Edit GraphCanvas.tsx
- 2026-08-03 [claude]: Edit UnifiedSearch.tsx
- 2026-08-03 [claude]: Edit UnifiedSearch.tsx
- 2026-08-03 [claude]: Edit UnifiedSearch.tsx
- 2026-08-03 [claude]: commit 15237925fa — fix(hub): honest telemetry + working Activity bell + Search redesign
- 2026-08-03 [claude]: Fixes shipped + verified live via Playwright: networkx base dep → Communities view renders 200 subsystem headers (was…
- 2026-08-03 [claude]: Status transitioned to complete via cos task-done.
