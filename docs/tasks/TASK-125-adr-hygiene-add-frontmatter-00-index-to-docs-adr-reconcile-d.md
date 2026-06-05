---
id: TASK-125
title: "ADR hygiene — add frontmatter + 00-index to docs/adr, reconcile docs-system naming rule"
swimlane: docs
kind: docs
epic: doc-system
labels: [docs-system, adr, audit-d1-f3, ready]
status: icebox
priority: P2
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-125: ADR hygiene — add frontmatter + 00-index to docs/adr, reconcile docs-system naming rule

**Outcome (one sentence):** All 6 ADRs carry the canonical frontmatter header (domain | layer:adr | ssot:true | updated), docs/adr/ gets a 00-index hub, and docs-system.md is reconciled with the actual docs/adr/ location + ADR-NNNN-slug naming — so ADRs are header-routable, indexable (pairs with the rag adr-path fix), and stop violating the doc system's own rules.

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- docs/adr/
- docs/governance/docs-system.md

## Work Log
