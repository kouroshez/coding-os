---
id: TASK-964
title: "governance: add the missing Verification-Matrix row for src/core/rules and src/core/skills"
swimlane: docs
kind: bug
epic: null
labels: [governance, ci, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-13
started: 2026-08-13
completed: 2026-08-13
agent_session: ses-claude-20260812-170221-1654
depends_on: []
blocked_by: []
references: []
---
# TASK-964: governance: add the missing Verification-Matrix row for src/core/rules and src/core/skills

## Outcome

Editing a core rule or skill names a verification command instead of silently staling `tests/golden/**` and turning the next release PR red.

## Read First

- AGENTS.md
- tests/test_verification_matrix.py

## Repro Steps

1. Edit `src/core/rules/git-workflow.md`.
2. Run the command the docs imply for a `.md` change — `make docs-lint` — which passes.
3. Push.
4. CI job "modularity safety net (golden + render smoke)" fails: 8 golden sections drift on `.claude/rules/git-workflow.md` / `.codex/rules/git-workflow.md`, which are rendered copies of the edited source.

Observed on PR #68 (release 0.3.17). The Modularity Map already states these paths reach ALL projects; the Verification Matrix has no row for them.

## Acceptance

- **Given** an agent edits `src/core/rules/*.md` or `src/core/skills/**`, **When** it consults AGENTS.md § Verification Matrix, **Then** a row names `uv run pytest tests/test_golden_parity.py tests/test_rules_fresh.py -q`.
- **Given** the new row, **When** `tests/test_verification_matrix.py` runs, **Then** every pytest target in it resolves.

## Work Log
- 2026-08-13 [claude]: Edit AGENTS.md
- 2026-08-13 [claude]: commit 1bd26e7866 — docs(agents): add the Verification-Matrix row for src/core/rules and src/core/skills
- 2026-08-13 [claude]: Status transitioned to complete via cos task-done.
