---
id: TASK-469
title: "Lighthouse strategy ADR: streamos breaks the dogfood monoculture (F)"
swimlane: docs
kind: docs
epic: audit-remediation-2026-06
labels: [audit-remediation, strategy, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-20
started: 2026-06-20
completed: 2026-06-20
agent_session: ses-claude-20260619-211916-fd8f
depends_on: []
blocked_by: []
references: []
---
# TASK-469: Lighthouse strategy ADR: streamos breaks the dogfood monoculture (F)

**Outcome (one sentence):** ADR-0012 records the decision to break the dogfood monoculture (the audit's master risk) by running the full cognitive loop on a real consumer app — streamos (Go+SvelteKit, already a registered/half-wired consumer) — with a falsifiable success test (non-degenerate outcome mix + a differential router rec + a learned pattern from non-INFRA work). The multi-week build is owner-driven and tracked on streamos's own board; this is the strategy + criteria, not meta-repo code.

## Read First
- docs/architecture/adr/0010-consumer-distribution-version-gate.md
- docs/governance/stack-maturity.md
- docs/engineering/learning-extraction.md

## Work Log
- 2026-06-20 [claude]: commit 8d5d6a88ba — docs(adr): ADR-0012 lighthouse consumer breaks the dogfood monoculture (F)
- 2026-06-20 [claude]: Status transitioned to complete via cos task-done.
