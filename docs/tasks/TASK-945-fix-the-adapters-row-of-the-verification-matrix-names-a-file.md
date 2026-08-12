---
id: TASK-945
title: "fix: the adapters row of the Verification Matrix names a file that does not exist"
swimlane: docs
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-12
started: 2026-08-11
completed: 2026-08-11
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-945: fix: the adapters row of the Verification Matrix names a file that does not exist

**Outcome (one sentence):** The Verification Matrix command for src/adapters/** runs the suites that actually exist, so following the matrix cannot produce a silent no-op instead of a verification.

## Read First
- AGENTS.md
- src/core/rules/test-discipline.md
- tests/test_adapter_parity.py

## Repro Steps
AGENTS.md Verification Matrix row `src/adapters/**` prescribes `uv run pytest tests/test_adapters.py tests/test_adapter_parity.py -q`. Run 2026-08-11: "ERROR: file or directory not found: tests/test_adapters.py / no tests ran in 0.03s" — exit non-zero, zero tests executed. The file was split into tests/test_adapters_claude.py, tests/test_adapters_codex.py and tests/test_adapters_skills.py and the matrix was never updated.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the matrix row for src/adapters/** **When** an agent copies the command verbatim **Then** it executes and reports a real pass/fail. **Given** every other matrix row **When** each command is executed **Then** none errors on a missing path.

## Work Log
- 2026-08-12 [claude]: Edit AGENTS.md
- 2026-08-12 [claude]: Edit test_verification_matrix.py
- 2026-08-12 [claude]: Edit test_verification_matrix.py
- 2026-08-12 [claude]: commit 80a6293166 — fix(docs): repair three Verification-Matrix rows that resolved to no tests
- 2026-08-12 [claude]: Found 3 dead rows not 1, plus a bare `python` row. Globs + tests/test_verification_matrix.py (23 tests); proved all 4…
- 2026-08-12 [claude]: Status transitioned to complete via cos task-done.
