---
id: TASK-942
title: "feat: resource lifetime on the error path is a named rule"
swimlane: core
kind: feature
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-08-12
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-942: feat: resource lifetime on the error path is a named rule

**Outcome (one sentence):** Every acquired resource — connection, transaction, file handle, lock, subprocess — has one owner and one release path that also runs when the body raises, stated as a rule the agent reads before writing the acquisition.

## Read First
- src/core/skills/clean-code/SKILL.md
- src/core/skills/clean-code/references/error-handling.md
- src/core/graph_os/backends/_sqlite_write.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the clean-code skill **When** an agent opens a resource **Then** the rule names the context-manager obligation and the failure it prevents. **Given** the sqlite write-lock incident **When** the rule is written **Then** it cites that concrete failure rather than an abstract principle. **Given** the rule lands **Then** make docs-lint passes.

## Work Log
