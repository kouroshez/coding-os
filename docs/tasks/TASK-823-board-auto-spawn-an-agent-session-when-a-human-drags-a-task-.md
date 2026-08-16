---
id: TASK-823
title: "Board: auto-spawn an agent session when a human drags a task icebox\u2192in_progress (settings-gated)"
swimlane: core
kind: feature
epic: null
labels: [hub, board, dispatch, ready]
status: archive
priority: P2
appetite: 3d
created: 2026-07-16
started: 2026-07-16
completed: 2026-07-16
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-823: Board: auto-spawn an agent session when a human drags a task icebox→in_progress (settings-gated)

**Outcome (one sentence):** With the hub setting enabled, a human drag of a ready task from icebox to in_progress dispatches an agent session on that task (reusing the sdk_dispatcher/formula dispatch path), binds it via agent_session, and the card immediately shows the live-agent pip; default OFF so existing drag behavior is unchanged.

## Read First
- docs/adapters/claude-sdk.md
- src/adapters/claude/sdk_dispatcher.py
- src/core/web/routes/board.py
- docs/engineering/hub-architecture.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the auto-spawn toggle is ON and a ready task is dragged icebox→in_progress from the panel **When** the move commits **Then** a dispatcher session is spawned with the task context and the transition is attributed to that session.
**Given** the toggle is OFF (default) **When** the same drag happens **Then** behavior is unchanged (human-attributed move, no spawn).
**Given** the dispatcher fails to spawn **When** the drag commits **Then** the move still succeeds and a visible stream row reports the spawn failure.

## Work Log
- 2026-07-16 [claude]: Edit hub-architecture.md
- 2026-07-16 [claude]: Edit settings.py
- 2026-07-16 [claude]: Edit settings.py
- 2026-07-16 [claude]: Edit settings.py
- 2026-07-16 [claude]: Edit settings.py
- 2026-07-16 [claude]: Edit board.py
- 2026-07-16 [claude]: Edit test_hub_settings_auto_spawn.py
- 2026-07-16 [claude]: Edit test_hub_settings_auto_spawn.py
- 2026-07-16 [claude]: Edit SettingsPage.tsx
- 2026-07-16 [claude]: Edit SettingsPage.tsx
- 2026-07-16 [claude]: Edit SettingsPage.tsx
- 2026-07-16 [claude]: Edit SettingsPage.tsx
- 2026-07-16 [claude]: Edit SettingsPage.tsx
- 2026-07-16 [claude]: Edit SettingsPage.tsx
- 2026-07-16 [claude]: Edit SettingsPage.tsx
- 2026-07-16 [claude]: Edit SettingsPage.tsx
- 2026-07-16 [claude]: Edit board.py
- 2026-07-16 [claude]: Edit board.py
- 2026-07-16 [claude]: Edit board.py
- 2026-07-16 [claude]: Edit board.py
- 2026-07-16 [claude]: Edit board.py
- 2026-07-16 [claude]: Edit board.py
- 2026-07-16 [claude]: Edit hub-architecture.md
- 2026-07-16 [claude]: Edit test_hub_settings_auto_spawn.py
- 2026-07-16 [claude]: commit 17b282b05d — feat(core): settings-gated board auto-spawn — drag icebox->in_progress dispatches an implementer
- 2026-07-16 [claude]: Reused the generic DispatchRequest/get_dispatcher seam (implementer formula, max_turns=100, 30min timeout) instead of…
