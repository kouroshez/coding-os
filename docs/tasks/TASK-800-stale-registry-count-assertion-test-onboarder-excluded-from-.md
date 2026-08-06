---
id: TASK-800
title: "Stale registry-count assertion: test_onboarder_excluded_from_formula_registry expects 11 but load_agent_registry returns 13"
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
# TASK-800: Stale registry-count assertion: test_onboarder_excluded_from_formula_registry expects 11 but load_agent_registry returns 13

**Outcome (one sentence):** The onboarder-exclusion test asserts the meaningful contract (onboarder absent from the formula registry) without a brittle absolute count that drifted stale when dispatch-only cards (repairer, distiller) were added.

## Read First
- tests/test_onboarder_role.py (`test_onboarder_excluded_from_formula_registry`)
- src/core/thinking_os/cognition.py (`load_agent_registry` — chat_only filter only)
- src/core/thinking_os/tests/test_cognition_supervisor.py (`test_agent_registry_has_expected_roles` — the contradicting count-pin, currently 13)

## Repro Steps
1. `uv run pytest tests/test_onboarder_role.py::test_onboarder_excluded_from_formula_registry -q`
2. The test asserts `len(load_agent_registry()) == 11`; the registry actually holds 13 (11 composable roles + dispatch-only cards repairer + distiller).
Expected: green — onboarder excluded, count matches reality.
Actual: fails `13 != 11`. Pre-existing (predates the repairer/distiller cards); surfaced during the memory-remediation epic, NOT caused by it — it fails identically with those changes absent. `load_agent_registry` filters only `chat_only`, so dispatch-only cards legitimately count.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the agent registry includes dispatch-only cards alongside the 11 composable roles,
- **When** `test_onboarder_excluded_from_formula_registry` runs,
- **Then** it passes by asserting `"onboarder" not in reg` (the real contract) plus a count that matches the registry's actual size, and the two count-pins (this test and test_agent_registry_has_expected_roles) agree on one number.

## Work Log
- 2026-07-06 [claude]: Edit test_onboarder_role.py
- 2026-07-06 [claude]: Edit repairer.md
- 2026-07-06 [claude]: Fixed both stale count-pins in test_onboarder_role.py: registry pin 11→13 (dispatch-only cards repairer+distiller…
