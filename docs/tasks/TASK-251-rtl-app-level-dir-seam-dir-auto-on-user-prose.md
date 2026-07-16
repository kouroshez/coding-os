---
id: TASK-251
title: "RTL: app-level dir seam + dir=auto on user prose"
swimlane: core
kind: feature
epic: hub-redesign
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260608-024900-f2b0
depends_on: []
blocked_by: []
references: []
---
# TASK-251: RTL: app-level dir seam + dir=auto on user prose

**Outcome (one sentence):** Add an app-level dir seam and dir=auto on user-authored prose so the Hub is RTL-ready.

## Read First
- src/core/web/ui/src/index.css — base + theme tokens.
- src/core/web/ui/src/layout/HubPrimitives.tsx (SubNav) + src/core/web/ui/src/components/Modal.tsx — convert left/right to logical properties.
- src/core/web/ui/src/features/cognition/ChatList.tsx — already uses dir=auto (the pattern to follow).

## Context / Approach
Convert physical left/right to CSS logical properties (margin-inline-*, inset-inline-*, justify-self) at the primitive layer so SubNav's grid, Modal close-button, and the chat sidebar mirror under RTL. Wrap every agent/user-authored prose container in dir=auto. Add an app-level dir seam (LTR default) so a future locale flip is config, not a rewrite. The owner types Persian — do this at the primitive layer (cheap now, a rewrite later).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** dir=rtl, **When** rendering, **Then** SubNav/Modal/chat-sidebar mirror correctly.
- **Given** user prose with RTL text, **When** rendered, **Then** its container uses dir=auto.

## Work Log
- 2026-06-08 [claude]: Added direction.ts app-level dir seam (VITE_HUB_DIR, LTR default) called from main.tsx; dir=auto on NewChatForm prose. M
