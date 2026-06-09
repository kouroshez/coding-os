---
id: TASK-025
title: "fix ruff format drift breaking CI Lint job"
swimlane: core
kind: bug
epic: null
labels: [ci, ruff, lint]
status: complete
priority: P0
appetite: "30m"
created: 2026-05-23
started: 2026-05-23
completed: 2026-05-23
agent_session: ses-claude-20260523-010526-e647
depends_on: []
blocked_by: []
references:
  - .github/workflows/ci.yml
  - src/core/hooks/_helpers/branch_guard_check.py
  - src/core/web/routes/audits.py
  - tests/test_branch_guard.py
---
# TASK-025: fix ruff format drift breaking CI

**Outcome (one sentence):** GitHub Actions CI Lint job stops failing on every commit — three files have been format-drift since TASK-012/013/014/015 landed (~5 days), cascading "CI Pass" to fail on every PR.

## Read First
- [.github/workflows/ci.yml](../../.github/workflows/ci.yml) — `ruff format --check` is enforced (lines 53-54), `ruff check` is informational `|| true`
- [src/core/hooks/_helpers/branch_guard_check.py](../../src/core/hooks/_helpers/branch_guard_check.py) — 1 of 3 drift files
- src/core/web/routes/audits.py (removed 2026-06-09) — 1 of 3
- [tests/test_branch_guard.py](../../tests/test_branch_guard.py) — 1 of 3

## Repro Steps
1. `uv run ruff format --check src/ tests/`
2. Output: `3 files would be reformatted, 446 files already formatted`
3. CI Lint job exits 1 → CI Pass cascades to fail (all matrix jobs marked skipped because Lint is the prerequisite).

Expected: 0 files would be reformatted. Actual: 3 — branch_guard_check.py, audits.py, test_branch_guard.py.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a push or PR to `main`
- **When** the GitHub Actions CI workflow runs
- **Then** the `ruff format --check` step exits 0 and the downstream matrix jobs (pytest, shellcheck, vitest+build, docs-lint) actually execute; CI Pass = green.

## Work Log
- 2026-05-23 — confirmed via `gh run view --log-failed` that all recent CI runs fail because of `ruff format --check` on 3 files (no other lint stage gates the build — `ruff check` is `|| true`, mypy `|| true`). Ran `uv run ruff format` on the 3 files → 3 files reformatted, 446 already-formatted; `--check` re-run reports 449 files clean. Diff total = 20 inserts / 13 deletes, pure whitespace + line-break normalization, no semantic change. Verified Lint step locally before commit. NOTE: `release-please` workflow fails separately with `Bad credentials` — requires a PAT with `contents: write` + `pull-requests: write`; out of scope here, raised as separate concern for the project owner.
- 2026-05-23 [claude]: Status transitioned to complete via cos task-done.
