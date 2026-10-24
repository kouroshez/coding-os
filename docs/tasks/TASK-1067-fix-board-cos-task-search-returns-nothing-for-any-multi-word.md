---
id: TASK-1067
title: "fix(board): cos_task_search returns nothing for any multi-word query"
swimlane: "board_os"
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
# TASK-1067: fix(board): cos_task_search returns nothing for any multi-word query

**Outcome (one sentence):** A natural-language task query returns the relevant tasks, as the tool docstring promises, instead of zero results whenever the query has more than one word.

## Read First
- docs/governance/task-lifecycle.md

## Repro Steps
1. cos_task_search("duplicate code ratchet clone groups gate verify") → count 0.
2. cos_task_search("symlink") → 8 results, every score 0.6 (the LIKE fallback), so the semantic path never answers.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** tasks titled with "symlink" and "duplicate" **When** cos_task_search("symlink version gate") runs **Then** TASK-462 is returned
- **Given** embeddings are unavailable **When** a multi-word query runs **Then** the fallback matches on the individual words

## Work Log
- 2026-10-24 [claude]: Status transitioned to complete via cos task-done.
