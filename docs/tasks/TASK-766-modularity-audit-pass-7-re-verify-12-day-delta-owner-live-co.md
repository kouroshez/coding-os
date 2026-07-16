---
id: TASK-766
title: "Modularity audit pass-7: re-verify 12-day delta + owner live-complaint hardening (Hub config UX dependents-view, default-profile clarity, adapter-discovery answer)"
swimlane: core
kind: chore
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-07-04
started: 2026-07-03
completed: 2026-07-03
agent_session: ses-claude-20260703-211332-9106
depends_on: []
blocked_by: []
references: []
---
# TASK-766: Modularity audit pass-7: re-verify 12-day delta + owner live-complaint hardening (Hub config UX dependents-view, default-profile clarity, adapter-discovery answer)

**Outcome (one sentence):** Pass-7 re-verified the modularity register against HEAD, fixed two 12-day-delta regressions (F9 orphan hooks + stale profile assertion) with a tool-owner guard + verify-suite to prevent recurrence, hardened the Hub Config dependency UX (reverse-deps + skills + pre-empted disable), and recorded the findings + owner live-complaint answers in the audit SSOT.

## Read First
- docs/engineering/modularity-audit-2026-06.md §12 (the pass-7 register)
- src/core/subsystems.yaml (module registry SSOT)
- src/core/thinking_os/tools/_shared.py (MCP tool gate)

## Acceptance (G/W/T)
- GIVEN the memory-v2 delta WHEN `pytest tests/test_cli.py::TestSubsystems tests/test_module_gating_smoke.py` runs THEN it is green (F9 + profile invariants restored).
- GIVEN a new unmapped MCP tool WHEN `test_every_registered_tool_has_a_module_owner_or_is_kernel` runs THEN it FAILs (reverse-totality guard, tool-side twin of the hook F9 invariant).
- GIVEN a module with enabled dependents WHEN the Hub Config Modules tab renders THEN its Disable button is greyed with the reason and a "Required by" column shows the reverse edge.

## Work Log
- 2026-07-03 [claude]: 31-agent adversarial pass-7 workflow (7 dims, refute-by-default): 22 confirmed/plausible, 2 over-claims refuted. Confirmed 2 RED-main regressions (F9 orphan hooks, stale profile assertion) + root cause (verify-suite mis-routing let it land silently).
- 2026-07-03 [claude]: ef5d46f2 — own 3 delta hooks (ensure-agent-memory-link/sync-agent-memory->memory, nudge-reentry->tasks), fix profile assertion, add reverse tool-owner guard + test-modules verify-suite. Verified: TestSubsystems+smoke 26 pass, gate-registry 18 pass, server --test ok.
- 2026-07-03 [claude]: 620a0db0 — audit doc §12 (pass-7 register + owner live-complaint answers: adapter discovery is data-driven, Hub UX gaps, tasks->docs is enforcement-locality) + inline subsystems.yaml rationale. docs-lint hard gate pass.
- 2026-07-03 [claude]: ab35f7e5 — Hub Config Modules tab: reverse-deps "Required by" column + skills count + pre-empted blocked Disable (frontend-only, derived client-side). ui-test 185 pass, ui-build clean.
