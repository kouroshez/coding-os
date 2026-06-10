---
id: TASK-299
title: "Concurrency + attribution hardening: atomic task-move CAS, advisory file-lock, panel attribution resolver, structured block-events"
swimlane: core
kind: feature
epic: panel-state-isolation
labels: [concurrency, attribution, memory, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-09
started: null
completed: null
agent_session: ses-claude-20260609-163314-6565
depends_on: []
blocked_by: []
references: []
---
# TASK-299: Concurrency + attribution hardening: atomic task-move CAS, advisory file-lock, panel attribution resolver, structured block-events

## Acceptance

**Given** two panels of the same agent read the same icebox task and both call `cos_task_move(task_id, to="in_progress")` concurrently,
**When** the status transition executes,
**Then** exactly one move succeeds (rowcount==1) and the other returns a `conflict` envelope (`already <status>`), proven by a regression test that simulates the interleaving.

**Given** a live sibling panel holds an advisory lock on `foo.py` (fresh heartbeat),
**When** this panel issues a Write/Edit to `foo.py`,
**Then** the hook WARNs (exit 0, never blocks) naming the holder; the lock is created with `O_EXCL` (no self-race), released on the next `git commit` of that path, and auto-expires on a short TTL — covered by a hook smoke test.

**Given** an MCP task write arrives while `$COS_PANEL_DIR` is set,
**When** `resolve_agent_session` runs,
**Then** the calling panel's `session-id` wins over the last-writer `.active-session` pointer — covered by a resolver unit test.

**Given** a deterministic hook-block recurs,
**When** the learning miner runs,
**Then** confidence no longer wastefully saturates from raw count beyond the cap and the block is recorded as a structured signal, not only regex-parsed from the text log — covered by a learning test.
