---
id: TASK-836
title: "Hub UI structural: decompose God-files + adopt typed api-client everywhere (audit backlog)"
swimlane: core
kind: refactor
epic: null
labels: [hub, frontend, audit, backlog, ready]
status: blocked
priority: P3
appetite: 1d
created: 2026-07-17
started: 2026-07-24
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-836: Hub UI structural: decompose God-files + adopt typed api-client everywhere (audit backlog)

**Outcome (one sentence):** Decompose the God-files (CosBoardPage ~4,246L, ConfigPage ~1,841L, ChatView ~807L) into feature folders; route MemoryPage/DoctorPage and other raw-fetch pages through the shared api-client (kill hand-rolled per-page interfaces + Doctor's unscoped fetch('/metrics')); derive response types from the generated api-types.ts (single source of truth) + add a drift gate; fix SettingsPage's two-save-flow (bottom Save must persist Scheduled edits); add missing loading/error states (Dashboard/Roles/Onboarding); fix SupportFooter placeholder 404 links; tighten lint --max-warnings.

## Read First
- src/core/web/ui/src/lib/api-client.ts
- src/core/web/ui/src/lib/api-types.ts
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** CosBoardPage / ConfigPage / ChatView **When** each is decomposed into a feature folder **Then** no single module exceeds ~400 lines and the full vitest suite stays green (behavior unchanged).
- **Given** a page that reads an API response **When** it types that response **Then** it derives the type from the generated api-types.ts (paths[...]) so a producer rename fails typecheck — no hand-rolled interface, no double-.data class of bug.
- **Given** MemoryPage / DoctorPage **When** they call the backend **Then** they route through the shared api-client (project-scoped + CSRF), with no raw fetch and no unscoped fetch('/metrics').
- **Given** SettingsPage **When** the bottom "Save settings" is clicked **Then** it also persists the Scheduled Maintenance edits (single save flow), and Dashboard/Roles/Onboarding render explicit loading + error states.
- **When** tsc --noEmit and vitest run **Then** they pass.

## Work Log
- 2026-07-24 [claude]: Pre-work audit-premise verification (2026-07-24, claude) — read producers before touching code: (1) DoctorPage…
- 2026-07-24 [claude]: Edit api-client.ts
- 2026-07-24 [claude]: Edit MemoryPage.tsx
- 2026-07-24 [claude]: Edit MemoryPage.tsx
- 2026-07-24 [claude]: Edit MemoryPage.tsx
- 2026-07-24 [claude]: Edit MemoryPage.tsx
- 2026-07-24 [claude]: Edit MemoryPage.tsx
- 2026-07-24 [claude]: Edit MemoryPage.tsx
- 2026-07-24 [claude]: Edit MemoryPage.tsx
- 2026-07-24 [claude]: Edit MemoryPage.tsx
- 2026-07-24 [claude]: Edit MemoryPage.tsx
- 2026-07-24 [claude]: Edit MemoryPage.tsx
- 2026-07-24 [claude]: commit 489baf25e9 — refactor(hub): route MemoryPage/DoctorPage through api-client (TASK-836)
- 2026-07-24 [claude]: Edit support-links.ts
- 2026-07-24 [claude]: commit 4b1c46d2c7 — feat(hub): SettingsPage single-save flow — bottom Save flushes scheduled edits (TASK-836)
- 2026-07-24 [claude]: commit f631c232ec — refactor(hub): decompose ChatView (806L) into chat-turns + chat-turn-views (TASK-836)
- 2026-07-24 [claude]: commit e704ee232c — refactor(hub): extract board-shared (types/constants/helpers/context) from CosBoardPage (TASK-836)
- 2026-07-24 [claude]: commit e04b50d91f — refactor(hub): extract TaskDetailDrawer + history into task-detail from CosBoardPage (TASK-836)
- 2026-07-24 [claude]: commit 379bb3f7fb — refactor(hub): extract board modals/badges/panels from CosBoardPage (TASK-836)
- 2026-07-24 [claude]: commit f00ded827e — refactor(hub): extract TaskStickyCard/SwimlaneLabel + TopBar from CosBoardPage (TASK-836)
- 2026-07-24 [claude]: commit 96c2625c40 — chore(hub): tighten UI lint budget 200->30 max-warnings (TASK-836)
- 2026-07-24 [claude]: Autonomous execution 2026-07-24 (claude) — DONE + verified (tsc clean · 206 vitest green · 0 lint errors · vite build…
- 2026-07-24 [claude]: commit a677d44ac5 — chore(board): TASK-836 progress log — decomposition + api-client + save-flow (partial)
- 2026-07-24 [claude]: commit 8be4f2ecfe — refactor(hub): split board-panels into 4 panel modules all <400 (TASK-836)
- 2026-07-24 [claude]: Edit CosBoardPage.tsx
- 2026-07-24 [claude]: commit 6f6956c5a3 — refactor(hub): split board-modals into 4 modules all <400 (TASK-836)
- 2026-07-24 [claude]: commit 4be988d280 — refactor(hub): split task-detail into drawer + history + edit-form (TASK-836)
- 2026-07-24 [claude]: commit 77da2d381d — refactor(hub): extract git-tab-data (types/presets/tips) from GitTab (TASK-836)
- 2026-07-24 [claude]: Continued to completion of the sub-splits 2026-07-24 (claude) — DONE + verified (tsc clean, 206 vitest, 0 lint-err,…
- 2026-07-24 [claude]: commit 36ed46d113 — chore(board): TASK-836 sub-splits complete — 14/17 board modules <400, 3 cohesive over
