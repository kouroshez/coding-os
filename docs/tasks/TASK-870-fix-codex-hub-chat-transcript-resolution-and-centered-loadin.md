---
id: TASK-870
title: "Fix Codex Hub chat transcript resolution and centered loading/error states"
swimlane: core
kind: bug
epic: null
labels: [hub, codex, chat, ux, ready]
status: testing
priority: P1
appetite: 1d
created: 2026-08-03
started: 2026-08-03
completed: null
agent_session: ses-codex-mcp-86642
depends_on: []
blocked_by: []
references: []
---
# TASK-870: Fix Codex Hub chat transcript resolution and centered loading/error states

**Outcome (one sentence):** Opening a live Codex session from Hub resolves the correct transcript instead of returning chat-session-not-found, and loading/error/empty states are centered, modern, accessible, and recoverable.

## Read First
- src/core/web/ui/src/features/cognition/ChatView.tsx
- src/core/web/routes/cognition.py
- docs/engineering/agent-hub-orchestration.md
- src/core/web/ui/src/lib/api.ts

## Repro Steps
In Hub, select the active Codex session 019fc9f3-343c-7301-9981-89b6a87afd59 and choose open chat. The page displays 'chat session not found: <id>' while remaining indefinitely on a small top-left 'loading transcript…' label.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** an active Codex presence session with its runtime session id and an available Codex thread transcript
**When** the operator opens that chat from Hub
**Then** the bridge resolves the matching transcript, or renders an accurate terminal unavailable state without indefinite loading; loading/error/empty states are centered, accessible, and recoverable, and Claude chat behavior remains intact under targeted backend/UI tests and a live browser check.

## Work Log
- 2026-08-04 [codex]: Root cause confirmed: clicked Codex presence had a dead PID and no Codex thread record; SessionEnd bypassed payload…
- 2026-08-04 [claude]: Implemented manifest-loaded Codex transcript list/read, fixed SessionEnd identity closure, and centered accessible…
