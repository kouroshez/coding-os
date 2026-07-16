---
id: TASK-782
title: "Fix /code-review findings: verify-substitution drift (nextjs/wordpress) + revert day-one-red angular/spring-boot Group-A changes"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-07-04
started: 2026-07-04
completed: 2026-07-04
agent_session: ses-claude-20260703-210450-473d
depends_on: []
blocked_by: []
references: []
---
# TASK-782: Fix /code-review findings: verify-substitution drift (nextjs/wordpress) + revert day-one-red angular/spring-boot Group-A changes

**Outcome (one sentence):** The Group-A defects a max-effort review found are fixed: nextjs/wordpress VERIFY_* substitutions (which drive the agent-facing AGENTS.md matrix) match their verify block; stack-lint reads the matrix-driving substitution so it catches that drift; and the two changes that turned day-one verify RED (angular spec with no test runner, spring-boot spotless bound to a phase on unformatted Java) are reverted with follow-up tasks filed.

## Read First
- src/templates/_base/fragments/verification-matrix.md.tmpl (matrix renders from VERIFY_* substitutions, not verify: block)
- src/cli/stack_lint.py (_verify_runs_test)
- /code-review output: tasks/w229r091g.output

## Acceptance
- **Given** `cos stack-lint`, **When** it runs, **Then** no stack reports a decorative-test GAP and none reports HARD.
- **When** nextjs/wordpress render, **Then** VERIFY_<CAT>_SUITES include their test-* target and VERIFY_<CAT> runs the test.
- **Then** the angular spec + spring-boot spotless `<executions>` are removed, and the nextjs golden is recaptured so golden parity passes.

## Repro Steps
1. `/code-review ultra 955678c4..HEAD` returned 15 CONFIRMED findings.
2. nextjs/wordpress: verify: block wired to run tests but VERIFY_<CAT>_SUITES left lint-only → agent matrix skips the test.
3. angular `ng test` has no architect target; spring-boot `mvnw verify` now runs spotless on 4-space Java → both day-one RED.

## Work Log
- 2026-07-04 [claude]: Edit stack_lint.py
- 2026-07-04 [claude]: commit 37a7783b6d — fix(templates): sync nextjs/wordpress verify substitutions + revert day-one-red changes
- 2026-07-04 [claude]: commit e57c0319ae — chore(golden): recapture nextjs golden after verify-matrix + CI target sync
- 2026-07-04 [claude]: Status transitioned to complete via cos task-done.
