---
id: TASK-125
title: "ADR hygiene — add frontmatter + 00-index to docs/adr, reconcile docs-system naming rule"
swimlane: docs
kind: docs
epic: doc-system
labels: [docs-system, adr, audit-d1-f3, ready]
status: complete
priority: P2
appetite: "1d"
created: 2026-06-05
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-125: ADR hygiene — add frontmatter + 00-index to docs/adr, reconcile docs-system naming rule

**Outcome (one sentence):** All 6 ADRs carry the canonical frontmatter header (domain | layer:adr | ssot:true | updated), docs/adr/ gets a 00-index hub, and docs-system.md is reconciled with the actual docs/adr/ location + ADR-NNNN-slug naming — so ADRs are header-routable, indexable (pairs with the rag adr-path fix), and stop violating the doc system's own rules.

## Read First
- docs/adr/
- docs/governance/docs-system.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the doc system's own rules govern ADRs
- **When** a maintainer inspects `docs/architecture/adr/` and `docs/governance/docs-system.md` § Naming Rules
- **Then** all 5 ADRs carry canonical frontmatter (`domain:ARCH | layer:adr | ssot:true | updated:`), a `00-index.md` hub indexes them, AND the docs-system ADR naming rule reads `NNNN-slug.md` under `docs/architecture/adr/` (matching the actual files, no `ADR-` prefix) — so ADRs stop violating the doc system's own naming + location rules; `make docs-lint` link audit stays green.

## Work Log
- 2026-06-06 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-06 [claude]: committed 2f7acfb7: docs/governance/docs-system.md
