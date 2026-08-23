---
name: verification-matrix-must-match-ci
description: "The Verification Matrix omitted two subsystems CI actually tests, so edits to them reached CI unverified — diff the matrix against the workflow, not just against the file you touched."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6fa96ac8-74bf-4312-9d92-4b169467cec9
  modified: 2026-08-23T20:33:50.895Z
---

`AGENTS.md § Verification Matrix` had rows for `thinking_os`, `graph_os`, `board_os`, web, cli, adapters, templates — but **not** `src/core/logging_os/**` or `src/core/scheduled/**`, even though `.github/workflows/ci.yml` runs a pytest step for each. Editing `logging_os/__init__.py` therefore had no matrix row telling me to run its suite, and a `__all__` lock test (`test_public_surface_is_locked`) turned CI red on all three Python versions.

**Why:** the matrix is hand-maintained and CI is hand-maintained, and nothing compared them. `tests/test_verification_matrix.py` checks that every row still *collects* — it cannot see a suite that has no row at all. A missing row is silent in exactly the way a stale row is not.

**How to apply:** when touching an unfamiliar subsystem, run `grep -oE "pytest src/core/[a-z_]+/tests/" .github/workflows/ci.yml | sort -u` and check each against `AGENTS.md`; add any missing row before you finish. Both gaps are now closed, but the same hole reopens whenever a new subsystem suite is added to CI without a matrix row. Sibling of [[red-ci-gate-hides-a-backlog]] and [[fix-the-twin-of-every-guard-you-fix]].
