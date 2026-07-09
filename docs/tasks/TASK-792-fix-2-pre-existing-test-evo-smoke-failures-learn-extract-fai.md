---
id: TASK-792
title: "fix: 2 pre-existing test_evo_smoke failures (learn_extract failure-pattern + cross-persona root-cause mining)"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-07-05
started: null
completed: null
agent_session: ses-claude-20260704-210156-0ee9
depends_on: []
blocked_by: []
references: []
---
# TASK-792: fix: 2 pre-existing test_evo_smoke failures (learn_extract failure-pattern + cross-persona root-cause mining)

**Outcome (one sentence):** Two thinking_os suite tests fail on a clean tree (unrelated to any recent change): test_evo_smoke.py::TestS4DebuggerMultiBacktrack::test_failure_patterns_extracted_by_learn_extract and TestS8MultiPersonaFailureCorrelation::test_cross_persona_root_cause_mined. Root-cause and fix (or quarantine with a tracked reason) so the test-thinking_os matrix gate is honestly green again.

## Read First
- src/core/thinking_os/tests/test_evo_smoke.py
- src/core/thinking_os/tools/learning.py

## Repro Steps
On main at 90780f19 (also reproduced with all working-tree changes stashed): `uv run --extra rag pytest src/core/thinking_os/tests/test_evo_smoke.py::TestS4DebuggerMultiBacktrack::test_failure_patterns_extracted_by_learn_extract src/core/thinking_os/tests/test_evo_smoke.py::TestS8MultiPersonaFailureCorrelation::test_cross_persona_root_cause_mined -q` → 2 failed in ~2.7s (AssertionError at test_evo_smoke.py:623). Full suite: 2 failed, 1478 passed. Discovered incidentally by TASK-790's matrix gate; proven pre-existing via git-stash on a clean tree.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a clean checkout of main
- **When** the two named test_evo_smoke tests run
- **Then** they pass (root cause fixed) OR are explicitly quarantined with a linked reason, so the test-thinking_os matrix suite is green and enforce-verify no longer records a FAIL for unrelated work.

## Work Log
