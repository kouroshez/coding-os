---
id: TASK-269
title: "Unify the 3 duplicated SSE chat readers into one shared consumeSse helper"
swimlane: core
kind: refactor
epic: hub-redesign
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-618-2ab7
depends_on: []
blocked_by: []
references: []
---
# TASK-269: Unify the 3 duplicated SSE chat readers into one shared consumeSse helper

**Outcome (one sentence):** NewChatForm, ChatView, and the board's AI-draft modal all consume one shared consumeSse frame-reader in src/lib/chat-stream.ts instead of re-implementing the fetch+reader+frame-split loop three ways, so the streaming protocol is edited in exactly one place.

## Read First
- src/core/web/ui/src/features/cognition/NewChatForm.tsx — start() SSE loop (~80-136)
- src/core/web/ui/src/features/cognition/ChatView.tsx — send SSE loop (~187-239)
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx — AgentTaskModal run() SSE loop (~2512-2564)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the three chat surfaces, **When** they stream a turn, **Then** each calls the single consumeSse(endpoint, body, onFrame, signal) helper; the fetch+reader+`\n\n`-frame-split loop exists in exactly one file.
- **Given** each surface, **When** frames arrive, **Then** behaviour is unchanged — NewChatForm extracts text/tool/usage/session, ChatView pushes raw {event,payload} into liveEvents, the AI-draft modal extracts text — because per-frame interpretation stays in each caller's onFrame.
- **Given** a non-OK response or abort, **When** streaming fails, **Then** the caller's existing try/catch/finally still runs (consumeSse throws; callers catch as before).

## Work Log
- 2026-06-08 [claude]: Added src/lib/chat-stream.ts::consumeSse (typed SseFramePayload, no `any`) as the single SSE frame-reader. Refactored Ne
- 2026-06-08 [claude]: committed 067776d5: src/core/web/ui/src/features/cognition/ChatView.tsx, src/core/web/ui/src/features/cognition/NewChatF
