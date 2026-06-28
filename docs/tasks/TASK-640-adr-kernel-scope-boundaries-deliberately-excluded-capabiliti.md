---
id: TASK-640
title: "ADR: kernel scope boundaries (deliberately-excluded capabilities) + dispatch partially-revived"
swimlane: core
kind: docs
epic: multi-model-autonomy
labels: [adr, scope, governance, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-28
started: 2026-06-28
completed: 2026-06-28
agent_session: ses-claude-20260627-204916-f0ee
depends_on: []
blocked_by: []
references: []
---
# TASK-640: ADR: kernel scope boundaries (deliberately-excluded capabilities) + dispatch partially-revived

**Outcome (one sentence):** An ADR that (a) records the capabilities we deliberately will NOT build, each with a one-line rationale tied to our anti-overengineering and minimal-context values — distributed consensus, cross-machine federation, a compiled rule kernel, ANN/quantization vector indexes, a second learning store, and a multi-provider facade — so future agents do not reintroduce them; and (b) updates the dispatch-deferral ADR to 'partially revived' once cost routing + the independent reviewer ship, naming what stays deferred (parallel orchestration).

## Read First
- docs/governance/adr-role-dispatch-deferral.md
- src/core/rules/anti-overengineering.md
- docs/governance/constitution.md
- docs/architecture/adr/0013-pr-mode-multi-agent-git-workflow-consumer-only.md

## Work Log
- 2026-06-28 [claude]: Edit adr-role-dispatch-deferral.md
- 2026-06-28 [claude]: Edit adr-role-dispatch-deferral.md
- 2026-06-28 [claude]: Edit 0015-kernel-scope-boundaries-deliberately-excluded-capabilities.md
- 2026-06-28 [claude]: commit 84a4ef88f6 — feat(repair): budget-capped autonomous repair loop + dispatchable repairer
- 2026-06-28 [claude]: (a) New ADR-0015 (docs/architecture/adr/) records 6 deliberately-excluded capabilities — distributed consensus,…
- 2026-06-28 [claude]: Status transitioned to complete via cos task-done.
