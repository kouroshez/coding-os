---
id: TASK-301
title: "Harden task transition: restore MD on post-write failure + real two-connection concurrency regression test"
swimlane: core
kind: bug
epic: panel-state-isolation
labels: [concurrency, board, tests, ready]
status: testing
priority: P2
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: null
agent_session: ses-claude-20260609-163314-6565
depends_on: []
blocked_by: []
references: []
---
# TASK-301: Harden task transition: restore MD on post-write failure + real two-connection concurrency regression test

## Outcome

**Outcome (one sentence):** Close the file-vs-DB consistency window in `transition()` (snapshot the MD file and restore it on any post-write failure so a rolled-back transition leaves neither DB nor file changed) and add a real two-connection concurrency regression test proving the CAS serialises genuine concurrent transitions, not just single-threaded drift.

## Repro Steps

1. In `transition()`, let `_write_status_to_frontmatter` succeed, then force the history INSERT or `conn.commit()` to raise.
2. Observe: DB rolls back to the previous status, but the `.md` frontmatter still reads the new status — file is ahead of DB.
3. Concurrency: no existing test opens two real connections both running `BEGIN IMMEDIATE`; drift is only simulated single-threaded via `expected_from`.

## Read First

- src/core/board_os/workflow.py
- src/core/board_os/tests/test_workflow.py
- docs/engineering/state-files.md

## Acceptance

**Given** a transition whose MD frontmatter write succeeds but whose subsequent history INSERT or commit raises,
**When** `transition()` unwinds,
**Then** the DB rolls back AND the `.md` file is restored to its pre-transition content — proven by a test that injects a post-write failure.

**Given** two real SQLite connections to the same board both attempt `icebox→in_progress` on the same task concurrently,
**When** both run through `transition()`,
**Then** exactly one returns ok=True and the other returns ok=False with a transient / CAS-miss error — proven by a two-connection regression test.
