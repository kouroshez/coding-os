---
id: TASK-822
title: "Board: live per-card agent activity indicator (pulsing adapter pip) + open the live chat from the card"
swimlane: core
kind: feature
epic: null
labels: [hub, board, ux, ready]
status: archive
priority: P2
appetite: 2d
created: 2026-07-16
started: 2026-07-16
completed: 2026-07-16
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-822: Board: live per-card agent activity indicator (pulsing adapter pip) + open the live chat from the card

**Outcome (one sentence):** An in_progress card whose bound agent_session is live (presence active/working) shows a pulsing adapter-branded pip (adapter glyph + spinner ring) on the card; clicking it opens the session's live chat/trace view (existing /api/cognition chat + hook stream), so the human can watch the agent work in real time from the board.

## Read First
- docs/engineering/hub-architecture.md
- src/core/web/ui/src/features/cos-board/agentPresenceVisuals.ts
- src/core/web/routes/stream.py
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a task bound to a live agent session (presence active/working) **When** the board renders the card **Then** the card shows the adapter glyph pip with the pulse animation and a tooltip naming the session.
**Given** the pip is clicked **When** the session has a live/persisted transcript **Then** the chat/trace view for that session opens (deep link, no dead modal).
**Given** the session ends **When** presence flips offline **Then** the pulse stops without a page reload (SSE presence-updated already drives this).

## Work Log
- 2026-07-16 [claude]: Edit CosBoardPage.tsx
- 2026-07-16 [claude]: Edit CosBoardPage.tsx
- 2026-07-16 [claude]: Edit CosBoardPage.tsx
- 2026-07-16 [claude]: Edit CosBoardPage.tsx
- 2026-07-16 [claude]: Edit CosBoardPage.tsx
- 2026-07-16 [claude]: Edit CosBoardPage.tsx
- 2026-07-16 [claude]: Edit CosBoardPage.tsx
- 2026-07-16 [claude]: Edit agent-presence.sh
- 2026-07-16 [claude]: Edit presence.py
- 2026-07-16 [claude]: Edit types.ts
- 2026-07-16 [claude]: Edit agentPresenceVisuals.ts
- 2026-07-16 [claude]: Edit CosBoardPage.tsx
- 2026-07-16 [claude]: Edit agentPresenceVisuals.test.ts
- 2026-07-16 [claude]: Edit test_presence.py
- 2026-07-16 [claude]: commit dd052592da — feat(core): live agent pip on task cards — pulse while the bound session works, click opens its chat
- 2026-07-16 [claude]: Delivered as pure UI-join on existing presence inventory (no new backend surface — reuse-first) + review-driven…
