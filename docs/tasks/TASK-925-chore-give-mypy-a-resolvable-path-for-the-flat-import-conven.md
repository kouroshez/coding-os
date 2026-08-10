---
id: TASK-925
title: "chore: give mypy a resolvable path for the flat-import convention so import-not-found stops multiplying"
swimlane: core
kind: chore
epic: null
labels: [ci, tech-debt, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-08-10
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-925: chore: give mypy a resolvable path for the flat-import convention so import-not-found stops multiplying

**Outcome (one sentence):** mypy resolves the flat sibling imports used inside src/core/thinking_os (from database import …, from tools._shared import …, from _server_runtime import …) so the import-not-found class disappears and the ratchet BASELINE drops well below 4687 instead of rising every time a module is split.

## Work Log
