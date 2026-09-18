---
id: TASK-1031
title: "Dispatched role prompts inherit archived tasks from a stale session-id"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-31
started: null
completed: 2026-09-13
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-1031: Dispatched role prompts inherit archived tasks from a stale session-id

**Outcome (one sentence):** A dispatched child is told about this session's active task or about no task at all — never about a task belonging to another session.

## Read First
- src/core/thinking_os/tools/_dispatch_request.py (`_shared_context`)
- src/core/thinking_os/dispatcher_helpers.py (`render_shared_context`)
- [[TASK-1030]] — the stale session id that made this reach months back

## Repro Steps
1. Query the live board DB with a session id that owns no task:
   `SELECT task_id FROM tasks WHERE status IN ('in_progress','testing')
    ORDER BY CASE WHEN agent_session = ? THEN 0 ELSE 1 END, updated_at DESC LIMIT 1`
2. Measured 2026-09-13 with `ses-claude-NEWLY-MINTED-abcd`: returns TASK-1003,
   owned by `ses-claude-20260527-151803-0b9f`.
3. Root cause: `agent_session` sits in an ORDER BY CASE, so it ranks this
   session's task first but never excludes anyone else's — with LIMIT 1 the
   fallback branch always wins when this session owns nothing. Paired with the
   never-rotating panel id ([[TASK-1030]]), the inherited task could be months old.
Expected: no task, when this session owns none.
Actual: the newest foreign task, presented to the child as its own work — and
the child has no other channel to check it against (Codex dispatch runs
--sandbox read-only with mcp_servers={}).

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a session that owns no in_progress or testing task
**When** a role is dispatched from it
**Then** `shared_context` is empty and the child is told about no task.

**Given** a session that owns one task while another session owns a newer one
**When** a role is dispatched
**Then** the child receives this session's task, not the newer foreign one.

## Work Log
- 2026-09-14 [claude]: Measured against the live board DB: a session id owning no task was still handed TASK-1003 because agent_session sat…
- 2026-09-14 [claude]: Status transitioned to complete via cos task-done.
