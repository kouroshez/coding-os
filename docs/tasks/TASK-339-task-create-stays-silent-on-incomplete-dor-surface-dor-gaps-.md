---
id: TASK-339
title: "task-create stays silent on incomplete DoR \u2014 surface dor_gaps + ready hint in the create envelope"
swimlane: "board_os"
kind: chore
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 2h
created: 2026-06-10
started: 2026-06-10
completed: 2026-06-10
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-339: task-create stays silent on incomplete DoR — surface dor_gaps + ready hint in the create envelope

**Outcome (one sentence):** Every cos_task_create response (MCP + CLI + web) carries data.dor = {ready, gaps[]} computed by the existing evaluate_dor validator, so an agent that creates a placeholder/not-ready task sees the gaps immediately in the same envelope instead of discovering them at task-start.

## Work Log
- 2026-06-10 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-10 [claude]: commit 5931c037f9 — feat(board): task-create envelope echoes DoR state — gaps + ready + fix hint
