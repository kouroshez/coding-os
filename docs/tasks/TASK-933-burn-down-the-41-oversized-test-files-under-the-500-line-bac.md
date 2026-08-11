---
id: TASK-933
title: "Burn down the 41 oversized test files under the 500-line backstop"
swimlane: infra
kind: refactor
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-11
started: 2026-08-11
completed: 2026-08-11
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-933: Burn down the 41 oversized test files under the 500-line backstop

## Outcome

The 41 test files still over the 500-line backstop are split along real seams, so `check_file_size.py` reports zero offenders outside the four recorded exceptions.

## Read First
- [docs/engineering/ci-gates.md](../engineering/ci-gates.md) — the ratchet protocol, the split-parity guard, and the four recorded exceptions
- [src/core/skills/clean-code/SKILL.md](../../src/core/skills/clean-code/SKILL.md) — the five resolution mechanisms a split breaks
- [src/core/rules/anti-overengineering.md](../../src/core/rules/anti-overengineering.md) — sub-rule 6: cohesion decides, line count only backstops

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the 41 oversized files under `tests/` and `src/**/tests/`
- **When** each is split along a seam that owns an independently changeable concern
- **Then** `uv run python src/core/scripts/check_file_size.py` lists only the four exception files, every matrix suite keeps its current pass count, and `check_split_parity.py` reports OK for each split.

## Notes

Test files carry a trap the source burndown did not: pytest fixtures resolve at run time, so a split file that loses its `conn`-style fixtures fails only when executed — collection stays green. Move fixtures with the tests that use them, and remember `tests/test_cli.py` imports its suite classes by explicit name from `tests/_cli_suite/*`, so a new class is silently uncollected until added to that import list.

Several of these files are also pinned in the `BASELINE` of `tests/test_file_size_budget.py` — delete the entry once a file drops under `SOFT_LIMIT`; never raise one.

## Work Log
- 2026-08-11 [claude]: Edit split_pr.py
- 2026-08-11 [claude]: Edit test_cli.py
- 2026-08-11 [claude]: Edit split_tests.py
- 2026-08-11 [claude]: Edit split_tests.py
- 2026-08-11 [claude]: Edit split_tests.py
- 2026-08-11 [claude]: commit bd2a7e71a9 — test(thinking_os): split test_db.py into five suites along its schema and migration seams
- 2026-08-11 [claude]: Edit tidy.sh
- 2026-08-11 [claude]: Edit tidy.sh
- 2026-08-11 [claude]: Edit tidy.py
- 2026-08-11 [claude]: Edit do_split.py
- 2026-08-11 [claude]: Edit tidy.py
- 2026-08-11 [claude]: commit 4d81aea1b9 — test(thinking_os): split test_supervision.py into four suites by supervision concern
- 2026-08-11 [claude]: Edit split_tests.py
- 2026-08-11 [claude]: Edit split_tests.py
- 2026-08-11 [claude]: Edit tidy.py
- 2026-08-11 [claude]: Edit map_symbols.py
- 2026-08-11 [claude]: Edit hoist.py
- 2026-08-11 [claude]: Edit split_seed.py
- 2026-08-11 [claude]: Edit split_seed.py
- 2026-08-11 [claude]: Edit split_seed.py
- 2026-08-11 [claude]: Edit split_seed.py
- 2026-08-11 [claude]: Edit split_seed.py
- 2026-08-11 [claude]: Edit conftest.py
- 2026-08-11 [claude]: Edit conftest.py
- 2026-08-11 [claude]: commit d0e5b93244 — test(thinking_os): split seed_simulation, memory, evo_smoke and session suites
- 2026-08-11 [claude]: Edit batch1.sh
- 2026-08-11 [claude]: Edit batch2.sh
- 2026-08-11 [claude]: Edit split_polyglot.py
- 2026-08-11 [claude]: Edit split_polyglot.py
- 2026-08-11 [claude]: Edit split_graph_mcp.py
- 2026-08-11 [claude]: Edit batch3.sh
- 2026-08-11 [claude]: Edit split_subsystems.py
- 2026-08-11 [claude]: Edit split_by_regex.py
- 2026-08-11 [claude]: commit d475a13de3 — test(cli): split the four remaining _cli_suite parts and test_branch_guard
- 2026-08-11 [claude]: commit 46c7d4707b — test(hooks): split the last seven oversized suites in tests/
- 2026-08-11 [claude]: Edit test_file_size_budget.py
- 2026-08-11 [claude]: Edit SKILL.md
- 2026-08-11 [claude]: commit 759362d825 — style(tests): sort the imports the corpus-module qualification unsorted
- 2026-08-11 [claude]: Edit SKILL.md
- 2026-08-11 [claude]: Edit SKILL.md
- 2026-08-11 [claude]: commit 91f1fbeb2c — fix(skills): drop the live model id from the no-hardcoding example
- 2026-08-11 [claude]: All 41 split; zero Python files over 500 outside 3 recorded exceptions. Full sweep 7202 passed.
- 2026-08-11 [claude]: Status transitioned to complete via cos task-done.
