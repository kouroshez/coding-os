---
id: TASK-1061
title: "fix(adapters): MEMORY.md lesson counters churn a commit every session"
swimlane: adapters
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-10-24
started: 2026-10-24
completed: 2026-10-24
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1061: fix(adapters): MEMORY.md lesson counters churn a commit every session

**Outcome (one sentence):** The generated Trusted-lessons block in .agents/memory/MEMORY.md changes only when the lesson set or text changes, not when a times_seen counter ticks.

## Read First
- docs/engineering/learning-extraction.md

## Repro Steps
1. `git show ce0d9c5f` → the only change is `(seen 59×)` → `(seen 60×)` and `(seen 124×)` → `(seen 125×)`.
2. Source: src/adapters/claude/hooks/agent_memory_sync.py renders `_(seen N×)_` on every Stop.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the same lessons with a higher times_seen **When** render_mirror runs **Then** MEMORY.md is unchanged
- **Given** a new trusted lesson **When** render_mirror runs **Then** the block gains that line

## Work Log
- 2026-10-24 [claude]: Status transitioned to complete via cos task-done.
