---
id: TASK-899
title: "CI coverage gate: run pytest with --cov + fail_under and diff-cover on PRs"
swimlane: core
kind: chore
epic: null
labels: [quality, ci, coverage, ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-08-08
started: 2026-08-07
completed: null
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-899: CI coverage gate: run pytest with --cov + fail_under and diff-cover on PRs

**Outcome (one sentence):** CI enforces coverage fail_under=60 and >=80% patch coverage on PRs

## Work Log
- 2026-08-08 [claude]: Reused make coverage as SSOT for the CI job instead of a parallel pytest invocation — one source for the gate;…
