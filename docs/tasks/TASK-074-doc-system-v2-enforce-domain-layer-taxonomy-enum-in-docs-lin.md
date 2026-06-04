---
id: TASK-074
title: "doc-system-v2: enforce domain/layer taxonomy enum in docs-lint + reconcile canonical values with reality"
swimlane: docs
kind: feature
epic: doc-system-v2
labels: [taxonomy, lint, doc-system]
status: testing
priority: P1
appetite: "1d"
created: 2026-06-04
started: 2026-06-03
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-074: doc-system-v2: enforce domain/layer taxonomy enum in docs-lint + reconcile canonical values with reality

**Outcome (one sentence):** docs-lint validates frontmatter domain + layer against canonical enums (reconciled to include actually-used legitimate values e.g. engineering/architecture and to normalize clear typos e.g. playbooks→playbook), rejecting unknown values; the canonical enums become SSOT in docs-system.md + doc-cheat-sheet.md; make docs-lint stays EXIT 0 across every existing doc (no false breakage).

## Read First
- docs/engineering/doc-system-overhaul-roadmap.md
- src/core/scripts/docs-lint.sh
- docs/governance/docs-system.md
- docs/governance/_templates/doc-cheat-sheet.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `docs-lint.sh:70` accepts domain `[A-Z_]+` / layer `[a-z]+` (ANY value, no enum); the cheat-sheet's stated domain enum (PRODUCT/BACKEND/.../DOMAIN) diverges from actual meta usage (CORE/META/ADAPTERS/INFRA), and `playbooks` (plural, 2 docs: polyglot-extractor-roadmap.md, db-reset.md) is a typo for `playbook`.
- **When** canonical enums are defined as SSOT — DOMAIN {ALL,CORE,META,ADAPTERS,DOCS,OPS,INFRA,SECURITY,PRODUCT,BACKEND,FRONTEND,AI,MOBILE}, LAYER {index,policy,playbook,spec,adr,reference,runbook,postmortem,task,engineering,architecture,template,plan,contract,checklist} — in docs-system.md + doc-cheat-sheet.md and validated in docs-lint.sh; template placeholders (XXX/STACK_DOMAIN) exempt; docs lacking frontmatter skipped (G9, separate); the 2 `playbooks` typos normalized to `playbook`.
- **Then** docs-lint reports any out-of-enum domain/layer; `make docs-lint` stays EXIT 0 across all existing docs (advisory default — no false breakage); a deliberately-bad value (`layer:bogus`) IS flagged; a `COS_DOCS_LINT_STRICT=1` toggle gates (exit 1) so enforcement flips on once the G9 frontmatter backlog clears.

## Work Log
