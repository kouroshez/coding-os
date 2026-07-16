---
id: TASK-091
title: "Make task-driver swimlane routing config-driven (kill hardcoded-table drift)"
swimlane: docs
kind: docs
epic: null
labels: [skill, swimlane, drift, ready]
status: archive
priority: P1
appetite: "1d"
created: 2026-06-04
started: 2026-06-04
completed: 2026-06-04
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-091: Make task-driver swimlane routing config-driven (kill hardcoded-table drift)

**Outcome (one sentence):** task-driver SKILL.md no longer hardcodes a swimlane list that contradicts scrumban-config.yaml; it teaches the agent to discover lanes from config and how to add one.

## Read First
- src/core/skills/task-driver/SKILL.md
- src/core/board_os/config.py

## Work Log
- 2026-06-04 [claude]: Replaced the hardcoded swimlane routing table (meta/ops/cross — matched no config) with config-driven discovery guidance
