---
id: TASK-128
title: "Harden doc-anchor + doc-sync integrity — verify anchored path exists, opt-in strict sync, nav-breadcrumb lint"
swimlane: core
kind: bug
epic: doc-system
labels: [docs-system, enforcement, ssot, audit-d5-f3, ready]
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

# TASK-128: Harden doc-anchor + doc-sync integrity — verify anchored path exists, opt-in strict sync, nav-breadcrumb lint

**Outcome (one sentence):** The docs-first gate proves a relevant spec exists, not just that a marker string was written: enforce-doc-anchor BLOCKs when no anchored docs/ path resolves on disk (test -f), catching typos + hallucinated anchors (D5-F3); enforce-doc-sync gains an opt-in COS_ENFORCE_DOC_SYNC=strict gating mode for the public-symbol-removed case (D5-F5); docs-lint warns on missing > Nav: breadcrumb (34% of docs lack it, D1-F4).

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- src/core/hooks/enforce-doc-anchor.sh
- src/core/hooks/enforce-doc-sync.sh
- src/core/scripts/docs-lint.sh

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
