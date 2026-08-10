<!-- domain:OPS | layer:engineering | ssot:true | updated:2026-08-08 -->
# CI Quality Gates — SSOT

Every blocking gate in `.github/workflows/ci.yml`, what it enforces, and how its
baseline moves. GOVERNANCE.md points here; this doc owns the detail.

## The gates

| Gate | Command | Baseline / threshold | Direction |
|---|---|---|---|
| ruff lint | `uv run ruff check .` | 0 findings; burndown ignores in `pyproject.toml` (`SIM105`, `SIM102`, `E741`) | ignore list may only shrink |
| ruff format | `uv run ruff format --check .` | exact | — |
| Complexity | part of `ruff check` — `C901` (mccabe ≤20), `PLR0912` (branches ≤24), `PLR0913` (args ≤10), `PLR0915` (statements ≤100) | per-file baseline in `pyproject.toml` `per-file-ignores` (101 violations / 40 files, 2026-08-08) | baseline may only shrink; never add a file |
| mypy ratchet | `uv run python src/scripts/mypy_ratchet.py` | error count ≤ `BASELINE` in the script (4649, 2026-08-08 — see the exception log below) | count may only fall; lower `BASELINE` when you fix errors |
| Tests + coverage | `make coverage` | `fail_under` in `pyproject.toml` (62; measured 63) | ratchet toward 70 → 80 |
| Slow suite (nightly) | `make test-slow` + the graph phantom gate, on the `schedule` trigger only | 0 failures; phantom count ≤ baseline | **surfaced, not gating** — `CI Pass` emits a warning; see the order-fragility note below |
| diff-cover (PRs only) | `diff-cover coverage.xml --fail-under 80` | 80% on changed lines | fixed — see the scope note below |
| File-size ratchet | `tests/test_file_size_budget.py` | per-file `BASELINE` (48 files over the 800-line `SOFT_LIMIT`, 2026-08-10) | each entry may only fall; a file outside `BASELINE` may never cross `SOFT_LIMIT` |
| shellcheck | `shellcheck -S warning src/core/hooks/*.sh src/core/scripts/*.sh` | 0 warnings | fixed |
| docs-lint | `make docs-lint` | 0 findings | fixed |
| CodeQL / dependency-review | GitHub-native | high severity | fixed |

## Ratchet protocol (applies to every "may only shrink" baseline)

1. Fix the underlying finding (refactor below threshold, type the module, split the file).
2. Shrink the baseline in the same commit — delete the per-file-ignore entry,
   lower `BASELINE` (mypy count, or the file's line entry) / raise `fail_under`.
3. Never widen a baseline to land a change; the gate exists to make regressions
   loud. A deliberate exception needs a task + a line here explaining why.

Recorded exceptions:

- 2026-08-08 (TASK-920): mypy BASELINE 4599 → 4649. The mcp_tools/doctor
  splits relocated 166 existing errors under new module identities and the
  dual `board_os.*`/`core.board_os.*` import paths double-count some of them;
  a pre/post error-list diff confirmed no new untyped code. The gate caught
  the +410 implicit-re-export regression first, which WAS fixed (`__all__`).
- 2026-08-09 (TASK-921): mypy BASELINE 4649 → 4651. The gate caught a real
  regression from the new repair tests (wrong import path + unnarrowed
  `Optional`s) and that WAS fixed; the residual +2 sits inside the
  local↔CI counting gap (local reports 4635 for the same tree), so the
  baseline is re-measured from CI. **Always re-measure from a CI log** — a
  laptop number will silently under-set the gate. The failure output now
  prints per-file counts so the next rise is diagnosable without a CI
  round-trip.

## What each gate does NOT cover (scope honesty)

The gates are real, but two of them only ever see pull requests, and this repo
is trunk-based — the maintainer pushes straight to `main`:

- **diff-cover ≥80%** and **dependency-review** run on `pull_request` only.
  In practice that means Dependabot and release-please PRs; a hand-written
  commit pushed to `main` is never measured by either. Treat them as gates for
  *external contributions*, not as a guarantee over all code.
  Worse until 2026-08-10: diff-cover fetched the base branch with `--depth=1`,
  so `origin/<base>...HEAD` had no merge base and the step *crashed* on every
  PR. The gate had never measured a single line — it failed closed, blocking
  the whole Dependabot queue. A gate that only ever fails is not a gate.
- **Branch protection** requires `CI Pass` with `enforce_admins: false`, which
  is what keeps trunk pushes working. For the maintainer the check is therefore
  *post-push reporting*, not a pre-merge block — a red `main` is visible and
  must be fixed forward, not prevented.
- **`make docs-lint`** hard-gates the link audit; its front-matter and staleness
  half is advisory locally and only strict-gated on *changed* docs in CI.
- **The nightly slow suite is order-fragile**, so it reports rather than gates.
  Measured 2026-08-09: two back-to-back `make test-slow` runs on an identical
  tree failed on *different* sets — the second run cleared five fixed failures
  and surfaced two new ones (`TestPersonaGoFiber`) that had passed an hour
  earlier. Root cause class: tests inheriting ambient `COS_*` env and shared
  scaffold state (issue #39). Until a run is reproducible, `CI Pass` emits a
  warning instead of failing; gating on a flaky suite would just teach everyone
  to ignore a red `main`.

## mypy promotion path

`[tool.mypy]` is lenient globally with per-package `strict = true` overrides
(`thinking_os.tools.*`, `graph_os.backends.*`, `board_os.workflow`). The ratchet
holds the total error count while packages are promoted one at a time: type a
package, add it to the strict list, lower `BASELINE`. mypy becomes a plain
zero-error gate when `BASELINE` reaches 0.

## Local mirror

`pre-commit` runs ruff, ruff-format, and shellcheck on staged files — the fast
subset. mypy, coverage, and the ratchets run in CI and via their commands above.
