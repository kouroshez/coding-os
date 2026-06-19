---
id: TASK-454
title: "B-8: routing_weights has no decision consumer \u2014 fix doc drift + record keep-vs-delete decision (RAPTOR-1/3)"
swimlane: docs
kind: docs
epic: null
labels: [modularity-audit-pass3, RAPTOR-1, docs-update, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-19
started: 2026-06-19
completed: 2026-06-19
agent_session: ses-claude-20260619-063923-1c50
depends_on: []
blocked_by: []
references: []
---
# TASK-454: B-8: routing_weights has no decision consumer — fix doc drift + record keep-vs-delete decision (RAPTOR-1/3)

**Outcome (one sentence):** Resolve the audit RAPTOR-1/3 findings honestly without a risky subsystem change. Verified: route_model + route_skill rank from task_outcomes directly (routing.py:95/206); routing_weights is only rebuilt (recalculate_weights) + staleness-checked, never READ for a routing decision — a write-and-self-check loop. Decision: KEEP (do NOT delete), because its consumer is the cost-aware ranker that is multi-model Phase 1 (designed + scheduled, deferred-by-owner), and deletion is premature + high-blast-radius (Rule-9 migration v3/v26 + 15 tests). Do NOT wire route_model to it now (that IS Phase 1). Fix the real defects today: (1) the thinking_os-final-edition.md store table lies that cos_route_skill/model write/consume routing_weights — corrected to recalculate_weights via the outcome loop, marked not-yet-consumed; (2) cross-reference comment between the two deliberately-duplicated recalc bodies (routing.py vs the import-light hook helper routing_evolution.py) so the lockstep is explicit (the duplication is an intentional Rule-8 import-isolation tradeoff, NOT deduped); (3) record the decision in the audit SSOT register.

## Read First
- src/core/thinking_os/tools/routing.py
- src/core/hooks/_helpers/routing_evolution.py
- src/core/docs/thinking_os-final-edition.md
- docs/engineering/modularity-audit-2026-06.md

## Work Log
- 2026-06-19 [claude]: Edit thinking_os-final-edition.md
- 2026-06-19 [claude]: Edit thinking_os-final-edition.md
- 2026-06-19 [claude]: Edit thinking_os-final-edition.md
- 2026-06-19 [claude]: Edit routing.py
- 2026-06-19 [claude]: Edit routing_evolution.py
- 2026-06-19 [claude]: Edit modularity-audit-2026-06.md
- 2026-06-19 [claude]: commit 73be0269ce — docs(routing): correct routing_weights store-table drift + record KEEP decision (RAPTOR-1/3)
