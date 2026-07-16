---
id: TASK-271
title: "cos_task_show omits stored fields (epic, labels, agent_session, timestamps)"
swimlane: core
kind: chore
epic: hub-redesign
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-618-2ab7
depends_on: []
blocked_by: []
references: []
---
# TASK-271: cos_task_show omits stored fields (epic, labels, agent_session, timestamps)

**Outcome (one sentence):** cos_task_show returns the epic, labels, agent_session, started_at and completed_at fields it already stores in the DB, so programmatic callers get them without parsing the raw markdown body.

## Work Log
- 2026-06-08 [claude]: cos_task_show now selects + returns epic, labels (parsed from labels_json), agent_session, started_at, completed_at — th
- 2026-06-08 [claude]: committed fcb8c2a2: src/core/board_os/mcp_tools.py
