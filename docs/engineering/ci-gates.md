# CI Quality Gates — SSOT

Every blocking gate in `.github/workflows/ci.yml`, what it enforces, and how its
baseline moves. GOVERNANCE.md points here; this doc owns the detail.

## The gates

| Gate | Command | Baseline / threshold | Direction |
|---|---|---|---|
| ruff lint | `uv run ruff check .` | 0 findings; burndown ignores in `pyproject.toml` (`SIM105`, `SIM102`, `E741`) | ignore list may only shrink |
| ruff format | `uv run ruff format --check .` | exact | — |
| Complexity | part of `ruff check` — `C901` (mccabe ≤20), `PLR0912` (branches ≤24), `PLR0913` (args ≤10), `PLR0915` (statements ≤100) | per-file baseline in `pyproject.toml` `per-file-ignores` (101 violations / 40 files, 2026-08-08) | baseline may only shrink; never add a file |
| mypy ratchet | `uv run python src/scripts/mypy_ratchet.py` | error count ≤ `BASELINE` in the script (4599, 2026-08-08) | count may only fall; lower `BASELINE` when you fix errors |
| Tests + coverage | `make coverage` | `fail_under` in `pyproject.toml` (62; measured 63) | ratchet toward 70 → 80 |
| diff-cover (PRs) | `diff-cover coverage.xml --fail-under 80` | 80% on changed lines | fixed |
| File-size ratchet | `tests/test_file_size_budget.py` | `MAX_LINES` | may only fall |
| shellcheck | `shellcheck -S warning src/core/hooks/*.sh src/core/scripts/*.sh` | 0 warnings | fixed |
| docs-lint | `make docs-lint` | 0 findings | fixed |
| CodeQL / dependency-review | GitHub-native | high severity | fixed |

## Ratchet protocol (applies to every "may only shrink" baseline)

1. Fix the underlying finding (refactor below threshold, type the module, split the file).
2. Shrink the baseline in the same commit — delete the per-file-ignore entry,
   lower `BASELINE` / `MAX_LINES` / raise `fail_under`.
3. Never widen a baseline to land a change; the gate exists to make regressions
   loud. A deliberate exception needs a task + a line here explaining why.

Recorded exceptions:

- 2026-08-08 (TASK-920): mypy BASELINE 4599 → 4649. The mcp_tools/doctor
  splits relocated 166 existing errors under new module identities and the
  dual `board_os.*`/`core.board_os.*` import paths double-count some of them;
  a pre/post error-list diff confirmed no new untyped code. The gate caught
  the +410 implicit-re-export regression first, which WAS fixed (`__all__`).

## mypy promotion path

`[tool.mypy]` is lenient globally with per-package `strict = true` overrides
(`thinking_os.tools.*`, `graph_os.backends.*`, `board_os.workflow`). The ratchet
holds the total error count while packages are promoted one at a time: type a
package, add it to the strict list, lower `BASELINE`. mypy becomes a plain
zero-error gate when `BASELINE` reaches 0.

## Local mirror

`pre-commit` runs ruff, ruff-format, and shellcheck on staged files — the fast
subset. mypy, coverage, and the ratchets run in CI and via their commands above.
