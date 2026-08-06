---
id: TASK-798
title: "learn_extract stopped emitting failure-type patterns from backtrack root causes (S4/S8 evo_smoke red)"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-07-05
started: 2026-07-06
completed: 2026-07-06
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-798: learn_extract stopped emitting failure-type patterns from backtrack root causes (S4/S8 evo_smoke red)

**Outcome (one sentence):** `learn_extract` again mines a `memory_type='failure'` learned_pattern when ≥3 backtracks share a root cause, so the failure-learning loop closes and the S4/S8 evo_smoke tests pass.

## Read First
- src/core/thinking_os/tools/learning.py (`learn_extract` failure-pattern emission path)
- src/core/thinking_os/tests/test_evo_smoke.py (TestS4DebuggerMultiBacktrack, TestS8MultiPersonaFailureCorrelation)

## Repro Steps
1. `uv run --extra rag pytest src/core/thinking_os/tests/test_evo_smoke.py::TestS8MultiPersonaFailureCorrelation::test_cross_persona_root_cause_mined -v`
2. Seed 4 backtracks with root_cause="missing_context" + 10 outcomes; `failure_pattern_query` correctly reports count==4.
3. `learn_extract(min_occurrences=3)` returns status ok but creates NO row with `memory_type='failure'`.
Expected: a failure pattern whose text contains the shared root_cause.
Actual: `SELECT pattern FROM learned_patterns WHERE memory_type='failure'` is empty → assertion fails. Pre-existing regression, surfaced during TASK-797; bisect points at the learning.py lesson-refactor series (023b91fa "anatomy lessons require a recorded remedy", 7caf1987) which tightened emission conditions. NOT caused by the memory-remediation floor/changelog/drain changes.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ≥3 backtracks sharing one root_cause and enough outcomes to clear the extract threshold,
- **When** `learn_extract(min_occurrences=3)` runs,
- **Then** a `memory_type='failure'` learned_pattern is created whose text contains that root_cause, and TestS4/TestS8 pass without weakening their assertions.

## Work Log
- 2026-07-06 [claude]: Edit learning-extraction.md
- 2026-07-06 [claude]: Edit cognition.py
- 2026-07-06 [claude]: Edit cognition.py
- 2026-07-06 [claude]: Edit cognition.py
- 2026-07-06 [claude]: Edit learning.py
- 2026-07-06 [claude]: Root cause was NOT a regression to revert: doc (learning-extraction.md §2, the SSOT) already required "pair cause…
