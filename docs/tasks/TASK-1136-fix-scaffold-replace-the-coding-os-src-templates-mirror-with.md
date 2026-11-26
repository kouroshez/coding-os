---
id: TASK-1136
title: "fix(scaffold): replace the .coding-os/src/templates mirror with a sha baseline in managed-files.json"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-11-26
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1136: fix(scaffold): replace the .coding-os/src/templates mirror with a sha baseline in managed-files.json

**Outcome (one sentence):** Consumers carry no template mirror; refresh_stack_rules decides from recorded hashes; finding D1 of docs/engineering/harness-loading-audit-2026-11.md is closed.

## Read First
- docs/engineering/harness-loading-audit-2026-11.md
- src/cli/_init_scaffold.py

## Repro Steps
`cos init -t fastapi` writes .coding-os/src/templates/fastapi/ with 4 files byte-identical to src/templates/fastapi (audit D1).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh scaffold, **When** it is listed, **Then** .coding-os/src/templates does not exist.
- **Given** an installed stack rule, **When** `cos update` runs, **Then** an untouched rule is refreshed and a user-edited one is kept.

## Work Log
