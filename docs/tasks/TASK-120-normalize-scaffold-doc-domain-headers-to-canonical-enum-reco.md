---
id: TASK-120
title: "Normalize scaffold doc domain headers to canonical enum + reconcile docs-lint/docs-system enums"
swimlane: templates
kind: bug
epic: doc-system
labels: [docs-system, dogfood, lint, audit-d1-f2, ready]
status: icebox
priority: P1
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-120: Normalize scaffold doc domain headers to canonical enum + reconcile docs-lint/docs-system enums

**Outcome (one sentence):** Every scaffold doc header uses a domain in the canonical enum so a fresh cos init project passes make docs-lint clean (no day-one warning spam, no strict-mode hard fail). The 7 rogue domains (API/ARCH/AUTH/CONTENT/DESIGN/ENGINEERING/REACTNATIVE) are normalized to documented consumer values; docs-lint.sh + docs-system.md enums reconciled with the audit/playbooks layers real docs already use (D1-F1).

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- src/core/scripts/docs-lint.sh
- docs/governance/docs-system.md

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
