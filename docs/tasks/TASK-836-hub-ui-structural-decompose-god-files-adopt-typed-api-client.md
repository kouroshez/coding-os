---
id: TASK-836
title: "Hub UI structural: decompose God-files + adopt typed api-client everywhere (audit backlog)"
swimlane: core
kind: refactor
epic: null
labels: [hub, frontend, audit, backlog]
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
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
