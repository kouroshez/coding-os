---
id: TASK-933
title: "Burn down the 41 oversized test files under the 500-line backstop"
swimlane: infra
kind: refactor
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-08-11
started: null
completed: null
agent_session: null
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
