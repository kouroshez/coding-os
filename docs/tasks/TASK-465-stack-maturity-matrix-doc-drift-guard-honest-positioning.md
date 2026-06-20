---
id: TASK-465
title: "Stack maturity matrix doc + drift-guard (honest positioning)"
swimlane: docs
kind: docs
epic: audit-remediation-2026-06
labels: [audit-remediation, positioning, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-20
started: 2026-06-19
completed: 2026-06-19
agent_session: ses-claude-20260619-211916-fd8f
depends_on: []
blocked_by: []
references: []
---
# TASK-465: Stack maturity matrix doc + drift-guard (honest positioning)

**Outcome (one sentence):** docs/governance/stack-maturity.md states the honest tiered coverage (4 stable / 16 beta / 6 stub of 26 stacks) with maturity DERIVED from objective signals (golden fixture / full overlay / *-plain) rather than a self-declared stack.yaml field that can lie; a test re-derives from the filesystem so the matrix cannot drift; report S3 (claim-vs-maturity gap) and S4 (depth-over-breadth) are answered.

## Read First
- docs/engineering/doc-system-overhaul-roadmap.md
- src/templates/
- tests/golden/

## Work Log
- 2026-06-20 [claude]: Status transitioned to complete via cos task-done.
