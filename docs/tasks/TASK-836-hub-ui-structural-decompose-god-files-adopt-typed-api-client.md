---
id: TASK-836
title: "Hub UI structural: decompose God-files + adopt typed api-client everywhere (audit backlog)"
swimlane: core
kind: refactor
epic: null
labels: [hub, frontend, audit, backlog, ready]
status: icebox
priority: P3
appetite: 1d
created: 2026-07-17
started: null
completed: null
agent_session: null
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
