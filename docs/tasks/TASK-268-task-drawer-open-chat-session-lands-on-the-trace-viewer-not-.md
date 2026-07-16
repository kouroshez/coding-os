---
id: TASK-268
title: "Task drawer \"Open chat session\" lands on the trace viewer, not the resumable chat"
swimlane: core
kind: bug
epic: hub-redesign
labels: [ready]
status: archive
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
# TASK-268: Task drawer "Open chat session" lands on the trace viewer, not the resumable chat

**Outcome (one sentence):** The task drawer's "Open chat session" button opens the chat workspace (ChatView + follow-up composer) so the user can continue the conversation, instead of the read-only cognition trace viewer.

## Read First
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx — TaskChatLink (~3960, window.open target)
- src/core/web/ui/src/App.tsx — /p/:slug/workspace/chat/:sessionId route (~87)

## Repro Steps
1. Open a task that has an agent_session with a resolvable sdk_uuid; click "Open chat session".
2. A new tab opens at /p/<slug>/cognition/<uuid>?view=chat — the read-only trace viewer, with no composer to continue the chat.
Expected: lands on /p/<slug>/workspace/chat/<uuid> (ChatLanding → ChatView) where the follow-up composer can resume the session.
Actual: lands on the cognition trace viewer (CognitionPage) — dead-ends the "continue chatting" intent.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a task with a resolvable chat session, **When** "Open chat session" is clicked, **Then** it opens /p/<slug>/workspace/chat/<sdk_uuid> (the resumable ChatView with composer), not the cognition trace viewer.
- **Given** a task with no resolvable sdk_uuid, **When** the drawer renders, **Then** the button stays hidden (unchanged behaviour).

## Work Log
- 2026-06-08 [claude]: TaskChatLink now opens /p/<slug>/workspace/chat/<sdk_uuid> (ChatLanding → ChatView + follow-up composer) instead of /cog
- 2026-06-08 [claude]: committed 6c9f39f1: src/core/web/ui/src/features/cos-board/CosBoardPage.tsx
