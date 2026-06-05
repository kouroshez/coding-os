---
id: TASK-118
title: "cos init ships .gitignore + auto first commit — stop consumers committing the mutating runtime DB"
swimlane: cli
kind: feature
epic: doc-system
labels: [docs-system, dogfood, git, audit-d6-f1, ready]
status: icebox
priority: P1
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-118: cos init ships .gitignore + auto first commit — stop consumers committing the mutating runtime DB

**Outcome (one sentence):** Every cos init creates a .gitignore (excludes .coding-os/*.db, traces/, panels/, *.db-wal/shm) AND an initial 'chore: scaffold coding-os project' commit, so docs are tracked from line one and the binary runtime DB + agent-memory PII never enter git history. Skips both when nested in an existing repo.

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- src/cli/_init_helpers.py
- src/cli/main.py
- src/templates/_base/scaffold/

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
