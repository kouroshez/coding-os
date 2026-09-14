---
id: TASK-1004
title: "Three legacy files remain over the 500-line backstop, failing cos doctor"
swimlane: core
kind: chore
epic: null
labels: [quality, file-size, ready]
status: testing
priority: P3
appetite: 2d
created: 2026-08-17
started: null
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-1004: Three legacy files remain over the 500-line backstop, failing cos doctor

**Outcome (one sentence):** quality.file_size passes: the three remaining over-budget files are split along real cohesion seams, so cos doctor exits 0 and the backstop stops being permanently red.

## Work Log
- 2026-09-14 [claude]: Root cause was two file-size gates carrying two exemption lists, despite check_file_size.py's own docstring claiming…
