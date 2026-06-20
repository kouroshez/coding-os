---
id: TASK-424
title: "Cleanup tail \u2014 Hub-chat in-process presence + scope-leak + dedup (P13/P8/P10/P30/...)"
swimlane: infra
kind: refactor
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-15
started: 2026-06-15
completed: null
agent_session: ses-claude-20260620-015545-0bbe
depends_on: []
blocked_by: []
references: []
---
# TASK-424: Cleanup tail — Hub-chat in-process presence + scope-leak + dedup (P13/P8/P10/P30/...)

**Outcome (one sentence):** The post-builder cleanup tail is resolved so the web/adapter layer is internally consistent and healthy: the Hub chat writes its own presence (so it appears in the Live-agents HUD), sessions.py uses the gated state-dir resolver (no cross-project read leak), and remaining duplicated helpers / hardcoded literals are collapsed to their SSOTs.

## Read First
- src/core/web/routes/cognition.py
- src/core/web/routes/sessions.py
- src/core/web/routes/presence.py
- src/adapters/claude/sdk_dispatcher.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the Hub chat and the web routes, **When** a chat turn runs and the routes resolve state, **Then** the chat session is written to sessions/<resolved-sid>.json (stamped with the host pid) and appears in /api/presence, sessions.py applies the is_explicit_project_scope gate like its siblings, and the targeted route/presence tests pass.

## Work Log
- 2026-06-15 [claude]: P13 (b2f1426e) + P8 (5d185a51) LANDED. P13: chat_new/chat_send write Hub-chat presence via the adapter's unified writer
- 2026-06-20 [claude]: Archiving (no-necessary-now). Both load-bearing acceptance items already landed on main: P13 Hub-chat presence…
