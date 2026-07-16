---
id: TASK-185
title: "Task to chat click-through via sdk_uuid or in-tree snapshot fallback"
swimlane: core
kind: feature
epic: agent-hub
labels: [ready]
status: archive
priority: P2
appetite: "1d"
created: 2026-06-06
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260605-183120-db30
depends_on: []
blocked_by: []
references: []
---
# TASK-185: Task to chat click-through via sdk_uuid or in-tree snapshot fallback

**Outcome (one sentence):** A task's detail surfaces a link to the chat session that created it — resolving agent_session to the live SDK uuid (presence) for the cognition chat view, with the in-tree transcript snapshot already shown as the ended-session fallback.

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/core/web/routes/board.py
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx
- src/core/web/ui/src/pages/CognitionPage.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a task created during an attributed session
- **When** the user opens the task detail
- **Then** a new GET /api/board/task/{id}/chat-ref returns {agent_session, sdk_uuid, has_snapshot}; the modal shows an "open originating chat" action that deep-links to the cognition chat when sdk_uuid is known, is gracefully disabled when neither uuid nor snapshot exists, and the snapshot transcript stays visible for ended sessions. Route test + make ui-build green.

## Work Log
- 2026-06-06 [claude]: Added GET /api/board/task/{id}/chat-ref resolving agent_session to the live sdk_uuid (presence glob) + snapshot availabi
