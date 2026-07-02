---
id: TASK-765
title: "pytest must not bind the hub singleton port 9188 \u2014 a test run hijacked the live hub with its tmp project DB"
swimlane: infra
kind: bug
epic: null
labels: [hub, testing, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-07-02
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-765: pytest must not bind the hub singleton port 9188 — a test run hijacked the live hub with its tmp project DB

**Outcome (one sentence):** Test-spawned hub instances bind an ephemeral port (or are mocked), so a pytest run can never replace the live hub on 9188; the live panel always serves the real project DB.

## Read First
- docs/engineering/hub-architecture.md
- docs/engineering/test-governance.md

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the full test suite runs while the hub serves 9188, **When** tests finish, **Then** lsof shows the 9188 process still holds the real project DB (not a pytest tmp path)
- **Given** a hub-dependent test, **When** it starts a server, **Then** it binds port 0 (ephemeral) or a mock

## Work Log
