---
id: TASK-420
title: "Presence coherence for SDK/chat sessions \u2014 unify writer schema + GC + reader (P5/P6/P7/P31)"
swimlane: infra
kind: refactor
epic: null
labels: [ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-15
started: 2026-06-15
completed: 2026-06-15
agent_session: ses-claude-20260614-214422-d991
depends_on: []
blocked_by: []
references: []
---
# TASK-420: Presence coherence for SDK/chat sessions — unify writer schema + GC + reader (P5/P6/P7/P31)

**Outcome (one sentence):** SDK-spawned + Hub-chat sessions show in the Live-agents HUD with model/context chips: the dispatcher _presence_write matches the canonical 12-key schema in _helpers/presence_write.py and emits prompt events; the keyed HUD reader prefers the live panel session-id marker over the fossil flat path; orphaned tmp presence files keep the .json stem and are reaped by presence_gc.

## Read First
- src/adapters/claude/sdk_dispatcher.py
- src/core/hooks/_helpers/presence_write.py
- src/core/web/routes/presence.py
- src/core/hooks/_helpers/presence_gc.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** an SDK-spawned or Hub-chat presence file, **When** the dispatcher writes it and the Hub reader resolves the live session, **Then** the file carries model/sdk_uuid/used_tokens/context_updated_at (12-key parity with _helpers/presence_write.py), the keyed reader resolves the live panel session-id (not the fossil flat None), tmp files keep the .json stem and are reaped by presence_gc, and the presence + dispatcher tests pass.

## Work Log
- 2026-06-15 [claude]: Chunk 2 (P5/P6/P7/P31) LANDED in afc60510. Dispatcher _presence_write now emits the canonical 12-key schema (added model
