---
id: TASK-963
title: "governance: gate the irreversible PyPI publish and write down what an agent may merge alone"
swimlane: infra
kind: chore
epic: null
labels: [governance, supply-chain, ci, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-13
started: 2026-08-13
completed: 2026-08-13
agent_session: ses-claude-20260812-170221-1654
depends_on: []
blocked_by: []
references: []
---
# TASK-963: governance: gate the irreversible PyPI publish and write down what an agent may merge alone

**Outcome (one sentence):** The `pypi` environment requires a human approval before any publish, and the repo states in writing which merges an agent may make autonomously versus which need the maintainer. Scorecard Code-Review is documented as structurally unreachable rather than treated as a defect.

## Work Log
- 2026-08-13 [claude]: Edit git-workflow.md
- 2026-08-13 [claude]: Edit ci-gates.md
- 2026-08-13 [claude]: Edit ci-gates.md
- 2026-08-13 [claude]: commit c299b77add — docs(governance): gate irreversible publishes behind a human, and say why review cannot be bought he
- 2026-08-13 [claude]: Gate proven by execution, not config-reading: dispatched a real publish of v0.3.16; publish-pypi was created, held at…
- 2026-08-13 [claude]: Status transitioned to complete via cos task-done.
