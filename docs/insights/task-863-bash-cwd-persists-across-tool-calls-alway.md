<!-- domain:CLI | layer:reference | ssot:false | source:outcome_history#947 | updated:2026-08-03 -->
# TASK-863: Bash cwd persists across tool calls — always run matrix pytest with an absolute repo-root path (cd /repo && pytest tests/...) and treat "no tests ran" as failure: the verify ledger keys on exit code, so a 0-collected run poisons it with a false green until COS_TEST_FORCE=1.

**Date:** 2026-08-03  
**Domain:** CLI  
**Source task:** [TASK-863](../tasks/TASK-863-audit-cos-init-onboarding-skills-presets-deep-review-fix-gap.md)

## Key Insight

Bash cwd persists across tool calls — always run matrix pytest with an absolute repo-root path (cd /repo && pytest tests/...) and treat "no tests ran" as failure: the verify ledger keys on exit code, so a 0-collected run poisons it with a false green until COS_TEST_FORCE=1.

## What Failed

Ran the matrix pytest suite via run_in_background while the shell cwd was still src/core/web/ui — pytest collected 0 tests, exited 0, and the test-governor ledger recorded a FALSE GREEN for test-cli on that tree; the next legitimate run was then BLOCKed as "already green".

## What Worked

COS_TEST_FORCE=1 from the repo root re-ran the real suite; verifying the tail of the output file ("N passed") instead of trusting exit code 0.

## Links

- Pattern: `learned_patterns#339` — retrievable via `cos_details`
- History: `outcome_history#947`
