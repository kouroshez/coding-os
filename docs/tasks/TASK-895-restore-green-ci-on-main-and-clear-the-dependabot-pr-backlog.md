---
id: TASK-895
title: "Restore green CI on main and clear the Dependabot PR backlog after the repo rebuild"
swimlane: infra
kind: chore
epic: null
labels: [ci, release, dependencies]
status: "in_progress"
priority: P1
appetite: 1d
created: 2026-08-06
started: 2026-08-06
completed: null
agent_session: ses-claude-20260803-180632-5fca
depends_on: []
blocked_by: []
references: []
---

# TASK-895: Restore green CI on main and clear the Dependabot PR backlog after the repo rebuild

**Outcome (one sentence):** main is green, 0.3.5 is on PyPI, and the 3 open Dependabot PRs are merged or closed with a stated reason.

## Work Log
- 2026-08-06 [claude]: commit 4251243bb2 — fix(ci): refresh golden fixtures and scaffold manifest for the CLAUDE.md entrypoint
- 2026-08-06 [claude]: commit 2903f7b91d — ci: move the frontend jobs and UI build image off end-of-life Node 20
