---
id: TASK-1117
title: "fix(hooks): the humanizer audit message tells the agent to reply in the user's language"
swimlane: "board_os"
kind: bug
epic: null
labels: [hooks, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-11-24
started: 2026-11-24
completed: 2026-11-24
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1117: fix(hooks): the humanizer audit message tells the agent to reply in the user's language

**Outcome (one sentence):** The enforce-humanizer-audit block message ends by telling the agent to write its report in the language of the user's latest message, so an English hook message no longer switches a Persian conversation to English.

## Read First
- src/core/hooks/enforce-humanizer-audit.sh
- .agents/memory/reply-in-the-users-language.md

## Repro Steps
Twice on 2026-11-24 the Stop hook's English audit message made the agent answer a Persian-speaking user in English, though the global rule and a memory both say English hook text is never a reason to switch.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the hook blocks a turn for an unaudited draft, **When** it prints its message, **Then** the message says to write the reply in the language of the user's latest message.
- **Given** the edit, **When** verify-hooks and the hook tests run, **Then** they pass.

## Work Log
- 2026-11-24 [claude]: commit a9a0547384 — fix(hooks): the humanizer audit message tells the agent to reply in the user's language
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
