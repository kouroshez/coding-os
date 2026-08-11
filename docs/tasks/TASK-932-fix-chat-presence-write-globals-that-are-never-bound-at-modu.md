---
id: TASK-932
title: "Fix _chat_presence_write globals that are never bound at module level"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-08-11
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-932: Fix _chat_presence_write globals that are never bound at module level

## Outcome

`_chat_presence_write` writes the Hub-chat presence file on first call instead of silently swallowing a `NameError`, so a chat session shows as live in the Sessions panel.

## Read First
- [src/core/web/routes/_cognition_chat_sdk.py](../../src/core/web/routes/_cognition_chat_sdk.py) — holds `_chat_presence_write` after the batch-eleven split
- [docs/engineering/state-files.md](../engineering/state-files.md) — presence file ownership

## Repro Steps
1. Start the Hub (`cos hub start`) and open a Cognition chat on any project.
2. Watch `.coding-os/<agent>/` for the chat presence file.
Expected: a presence entry appears and the session shows live.
Actual: nothing is written. `_chat_presence_write` declares `global _CHAT_PRESENCE_WRITER, _CHAT_PRESENCE_TRIED`, but neither name is ever bound at module level, so the first read raises `NameError` straight into the function's own `except Exception` and the write is skipped forever.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh process where neither module global has been assigned
- **When** `_chat_presence_write` is called for the first time
- **Then** it initialises both globals at module scope, writes the presence file, and a regression test asserts the file exists (the current code raises `NameError` internally and writes nothing).

## Notes

Found during the TASK-928 burndown while moving the function verbatim; deliberately not fixed there so a behaviour change would not ride inside a refactor commit.

## Work Log
