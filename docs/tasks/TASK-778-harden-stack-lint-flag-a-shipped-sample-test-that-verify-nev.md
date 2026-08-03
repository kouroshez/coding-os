---
id: TASK-778
title: "Harden stack-lint: flag a shipped sample test that verify never runs (decorative-test guard)"
swimlane: core
kind: chore
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-07-04
started: 2026-07-04
completed: 2026-07-04
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-778: Harden stack-lint: flag a shipped sample test that verify never runs (decorative-test guard)

**Outcome (one sentence):** cos stack-lint gains a soft check so a community-contributed (or existing) work-surface stack that ships a sample test but whose verify command runs no test suite is reported — preventing the nextjs-class regression where a test ships but is never exercised day-one.

## Work Log
- 2026-07-04 [claude]: Edit stack_lint.py
- 2026-07-04 [claude]: Edit stack_lint.py
- 2026-07-04 [claude]: Edit test_cli.py
- 2026-07-04 [claude]: Edit test_cli.py
- 2026-07-04 [claude]: commit a66f83bc0f — test(cli): update assertions for plain-language refusal + nextjs CI test leg
- 2026-07-04 [claude]: Status transitioned to complete via cos task-done.
