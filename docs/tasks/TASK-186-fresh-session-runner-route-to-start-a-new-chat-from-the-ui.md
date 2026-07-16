---
id: TASK-186
title: "Fresh-session runner route to start a new chat from the UI"
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
# TASK-186: Fresh-session runner route to start a new chat from the UI

**Outcome (one sentence):** A new chat/session can be started from the UI (optional role + prompt + model): POST /api/cognition/chat runs a fresh headless Claude SDK query (no resume), SSE-streams it, captures the minted session_id, and the existing chat browser/send takes over. Claude-only.

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/core/web/routes/cognition.py
- src/adapters/claude/sdk_dispatcher.py
- src/core/web/ui/src/features/cognition/ChatView.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Claude Agent SDK is available
- **When** the user submits a prompt (+ optional role + model) from a New-chat form
- **Then** POST /api/cognition/chat starts a fresh session (no resume=), SSE-streams the turn, emits a `session` event with the minted session_id, and the UI opens that chat; when the SDK is absent it returns a clear `unavailable` envelope and the UI disables the form. Route guard tests + make ui-build green.

## Work Log
- 2026-06-06 [claude]: Added POST /api/cognition/chat: fresh Claude session with a pre-set session_id (no resume), permission_mode=dontAsk + se
