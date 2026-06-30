---
id: TASK-653
title: "Dedup golden SECTIONS into one SSOT module imported by capture_golden + test_golden_parity"
swimlane: cli
kind: refactor
epic: stack-completeness-v2
labels: [golden, dedup, wave-2, ready]
status: complete
priority: P3
appetite: 1d
created: 2026-06-30
started: 2026-06-30
completed: 2026-06-30
agent_session: ses-claude-20260630-012042-78c9
depends_on: []
blocked_by: []
references: []
---
# TASK-653: Dedup golden SECTIONS into one SSOT module imported by capture_golden + test_golden_parity

**Outcome (one sentence):** The golden SECTIONS list is defined once in a single importable module; both src/scripts/capture_golden.py and tests/test_golden_parity.py import it instead of each hand-syncing a copy (removing the "must stay in lock-step" hazard).

## Read First
- src/scripts/capture_golden.py
- tests/test_golden_parity.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the new SSOT module, **When** capture_golden.py and test_golden_parity.py run, **Then** both import SECTIONS from it (no literal list duplicated) and test_golden_parity passes.
**Given** `uv run python src/scripts/capture_golden.py --help`, **When** invoked, **Then** it imports with no ModuleNotFoundError.
**Given** the dedup, **When** grepping, **Then** exactly one `SECTIONS: list[tuple` definition exists in the repo.

## Work Log
- 2026-06-30 [claude]: Edit golden_sections.py
- 2026-06-30 [claude]: Edit capture_golden.py
- 2026-06-30 [claude]: Edit capture_golden.py
- 2026-06-30 [claude]: Edit test_golden_parity.py
- 2026-06-30 [claude]: Edit test_golden_parity.py
- 2026-06-30 [claude]: Edit test_golden_parity.py
- 2026-06-30 [claude]: commit bf4ff33605 — refactor(golden): single SECTIONS SSOT module for capture + parity test
- 2026-06-30 [claude]: Edit tsconfig.json
- 2026-06-30 [claude]: commit d7ebfa462f — fix(node-express): exclude test files from pre-install tsc typecheck
