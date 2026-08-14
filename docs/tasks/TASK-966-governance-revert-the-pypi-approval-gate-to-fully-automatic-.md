---
id: TASK-966
title: "governance: revert the PyPI approval gate to fully automatic per operator decision"
swimlane: infra
kind: chore
epic: null
labels: [governance, ci, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-14
started: 2026-08-13
completed: 2026-08-13
agent_session: ses-claude-20260812-170221-1654
depends_on: []
blocked_by: []
references: []
---
# TASK-966: governance: revert the PyPI approval gate to fully automatic per operator decision

**Outcome (one sentence):** The pypi environment publishes without a manual approval again, and git-workflow.md + ci-gates.md describe that reality instead of a gate that no longer exists.

## Work Log
- 2026-08-14 [claude]: Edit git-workflow.md
- 2026-08-14 [claude]: Edit ci-gates.md
- 2026-08-14 [claude]: commit fa3a087d23 — docs(governance): turn the PyPI approval gate off and record why the reversal is the lesson
- 2026-08-14 [claude]: Status transitioned to complete via cos task-done.
