---
id: TASK-202
title: "Strip development-phase milestone jargon from source comments and docstrings"
swimlane: infra
kind: chore
epic: null
labels: [cleanup, tech-debt, ready]
status: complete
priority: P2
appetite: "1d"
created: 2026-06-06
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-202: Strip development-phase milestone jargon from source comments and docstrings

**Outcome (one sentence):** Every dev-phase milestone label (Phase I/L/C/M/N/G/O/Q/EVO and sub-numbers) removed from source comments, docstrings, help-text and log messages; functional phase-strings (trajectory free-text field) and TASK-NNN traceability preserved; dead populate_board_from_phases.py deleted; coupled test assertion updated.

## Work Log
- 2026-06-06 [claude]: Stripped 409→35 Phase-jargon refs: workflow classified 353 edits + 46 functional KEEPs; applied (unmatched=0) + 9 residu
