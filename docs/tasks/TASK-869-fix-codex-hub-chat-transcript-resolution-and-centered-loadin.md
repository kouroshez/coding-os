---
id: TASK-869
title: "Fix Codex Hub chat transcript resolution and centered loading/error states"
swimlane: core
kind: bug
epic: null
labels: [hub, codex, chat, ux, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-08-03
started: null
completed: null
agent_session: ses-codex-019fc9ac-216e-7211-a224-dad139ff5712
depends_on: []
blocked_by: []
references: []
---
# TASK-869: Fix Codex Hub chat transcript resolution and centered loading/error states

**Outcome (one sentence):** Opening a live Codex session from Hub resolves the correct transcript instead of returning chat-session-not-found, and loading/error/empty states are centered, modern, accessible, and recoverable.

## Read First
- src/core/web/ui/src/features/cognition/ChatView.tsx
- src/core/web/routes/cognition.py
- docs/engineering/agent-hub-orchestration.md
- src/core/web/ui/src/lib/api.ts

## Repro Steps
In Hub, select the active Codex session 019fc9f3-343c-7301-9981-89b6a87afd59 and choose open chat. The page displays 'chat session not found: <id>' while remaining indefinitely on a small top-left 'loading transcript…' label.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- Given an active Codex presence session with an SDK/runtime id bridge, when the operator opens its chat from Hub, then the matching transcript loads or an accurate terminal unavailable state is shown without an infinite loading state.
- Given transcript loading, empty, not-found, or retryable failure, when ChatView renders, then the state is centered in the content pane with clear hierarchy, accessible status semantics, and a relevant retry/back action.
- Given Claude chat sessions, when the same routes are exercised, then existing Claude list/open/resume behavior remains intact.
- Given the fix, when targeted backend and UI tests plus a live Hub browser flow run, then Codex and Claude paths are both verified.

## Work Log
- 2026-08-04 [claude]: committed ba5b320d · 20 files
