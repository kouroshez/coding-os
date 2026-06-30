---
id: TASK-649
title: "Reconcile node-express VERIFY_BACKEND substitution vs verify[].cmd (eslint prefix) + golden recapture"
swimlane: templates
kind: chore
epic: stack-completeness-v2
labels: [node-express, drift, wave-2, golden, ready]
status: complete
priority: P3
appetite: 1d
created: 2026-06-30
started: 2026-06-30
completed: 2026-06-30
agent_session: ses-claude-20260630-012042-78c9
depends_on: []
blocked_by: []
references: []
---
# TASK-649: Reconcile node-express VERIFY_BACKEND substitution vs verify[].cmd (eslint prefix) + golden recapture

**Outcome (one sentence):** node-express's VERIFY_BACKEND substitution and its verify[].cmd express the same backend verify command (the fastapi convention where substitution == verify cmd), with a documented decision on which representation is canonical, and the operational .coding-os.yaml + AGENTS.md matrix + golden fixtures recaptured to match.

## Work Log
- 2026-06-30 [claude]: verify[].cmd + makefile lint-backend: dropped dead npx-eslint prefix (no eslint config; lint==tsc); now ==…
- 2026-06-30 [claude]: committed e2eaae36 · 1 file
