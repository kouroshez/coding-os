---
id: TASK-120
title: "Normalize scaffold doc domain headers to canonical enum + reconcile docs-lint/docs-system enums"
swimlane: templates
kind: bug
epic: doc-system
labels: [docs-system, dogfood, lint, audit-d1-f2, ready]
status: complete
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260527-151803-0b9f
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
1. Lint a stack's scaffold docs: `bash src/core/scripts/docs-lint.sh src/templates/<stack>/scaffold/docs`.
2. Observe domain-enum validation for django / nextjs / react-native.
Expected: zero "domain X not in canonical enum" warnings.
Actual (pre-fix): django emits `AUTH`, react-native emits 4× `REACTNATIVE`, nextjs emits `CONTENT`/`DESIGN`/`ENGINEERING` warnings.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a freshly scaffolded consumer project (django / nextjs / react-native)
- **When** docs-lint validates the scaffold docs' domain headers against the canonical enum
- **Then** every scaffold doc header uses a canonical domain — the 7 rogue values are gone (API/ARCH added earlier; AUTH→SECURITY, REACTNATIVE→MOBILE, DESIGN/ENGINEERING→FRONTEND, CONTENT→PRODUCT), `docs-lint.sh src/templates/*/scaffold/docs` emits zero "not in canonical enum" warnings, and docs-lint.sh + docs-system.md enums stay in sync (remap to existing canonical values — no enum growth).

## Work Log
- 2026-06-06 [claude]: Status transitioned to complete via cos task-done.
