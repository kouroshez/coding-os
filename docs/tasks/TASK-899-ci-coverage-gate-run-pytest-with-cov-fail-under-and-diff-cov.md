---
id: TASK-899
title: "CI coverage gate: run pytest with --cov + fail_under and diff-cover on PRs"
swimlane: core
kind: chore
epic: null
labels: [quality, ci, coverage, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-08
started: 2026-08-07
completed: 2026-08-08
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-899: CI coverage gate: run pytest with --cov + fail_under and diff-cover on PRs

**Outcome (one sentence):** CI enforces coverage fail_under=60 and >=80% patch coverage on PRs

## Read First
- docs/engineering/test-governance.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the coverage job in ci.yml running `make coverage`
- **When** src/core coverage drops below fail_under=60, or a PR's changed lines fall below 80% (diff-cover)
- **Then** the job fails and ci-pass blocks; on the current tree it passes (63% measured, CI run 31241481626 green)

## Work Log
- 2026-08-08 [claude]: Reused make coverage as SSOT for the CI job instead of a parallel pytest invocation — one source for the gate;…
- 2026-08-08 [claude]: Edit Makefile
- 2026-08-08 [claude]: Edit Makefile
- 2026-08-08 [claude]: Edit Makefile
- 2026-08-08 [claude]: Edit Makefile
- 2026-08-08 [claude]: Status transitioned to complete via cos task-done.
