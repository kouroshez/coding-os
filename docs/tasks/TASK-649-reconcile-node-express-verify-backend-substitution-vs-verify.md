---
id: TASK-649
title: "Reconcile node-express VERIFY_BACKEND substitution vs verify[].cmd (eslint prefix) + golden recapture"
swimlane: templates
kind: chore
epic: stack-completeness-v2
labels: [node-express, drift, wave-2, golden, ready]
status: icebox
priority: P3
appetite: 1d
created: 2026-06-30
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-649: Reconcile node-express VERIFY_BACKEND substitution vs verify[].cmd (eslint prefix) + golden recapture

**Outcome (one sentence):** node-express's VERIFY_BACKEND substitution and its verify[].cmd express the same backend verify command (the fastapi convention where substitution == verify cmd), with a documented decision on which representation is canonical, and the operational .coding-os.yaml + AGENTS.md matrix + golden fixtures recaptured to match.

## Work Log
