---
id: TASK-128
title: "Harden doc-anchor + doc-sync integrity \u2014 verify anchored path exists, opt-in strict sync, nav-breadcrumb lint"
swimlane: core
kind: bug
epic: doc-system
labels: [docs-system, enforcement, ssot, audit-d5-f3, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-05
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-128: Harden doc-anchor + doc-sync integrity — verify anchored path exists, opt-in strict sync, nav-breadcrumb lint

**Outcome (one sentence):** The docs-first gate proves a relevant spec exists, not just that a marker string was written: enforce-doc-anchor BLOCKs when no anchored docs/ path resolves on disk (test -f), catching typos + hallucinated anchors (D5-F3); enforce-doc-sync gains an opt-in COS_ENFORCE_DOC_SYNC=strict gating mode for the public-symbol-removed case (D5-F5); docs-lint warns on missing > Nav: breadcrumb (34% of docs lack it, D1-F4).

## Read First
- src/core/hooks/enforce-doc-anchor.sh
- src/core/hooks/enforce-doc-sync.sh
- src/core/scripts/docs-lint.sh

## Repro Steps
1. Record a hallucinated/typo doc-anchor: `write-state.sh .doc-anchor "docs/does-not-exist.md"`.
2. Edit a code file. enforce-doc-anchor currently PASSES (it only checks the marker is non-empty, never that the path resolves on disk) — so a hallucinated anchor satisfies the docs-first gate.
Expected: the gate BLOCKs when no anchored docs/ path exists on disk; docs-lint warns when a doc lacks a `> Nav:` breadcrumb.
Actual: marker-string presence alone passes; docs-lint has no nav-breadcrumb check; enforce-doc-sync can never gate even when opted in.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a `.doc-anchor` whose docs/ path(s) do not resolve on disk
- **When** a code Write/Edit triggers enforce-doc-anchor
- **Then** the hook BLOCKs (exit 2) with a repair message; AND enforce-doc-sync exits 2 only when COS_ENFORCE_DOC_SYNC=strict (warn otherwise); AND docs-lint emits a warning for any doc missing a `> Nav:` breadcrumb — all verified by `make verify-hooks`.

## Work Log
- 2026-06-06 [claude]: D5-F3: enforce-doc-anchor now extracts docs/*.md tokens from the anchor and BLOCKs when none resolve on disk (task-based
- 2026-06-06 [claude]: committed e65aafe8: src/core/hooks/enforce-doc-anchor.sh, src/core/hooks/enforce-doc-sync.sh, src/core/scripts/docs-lint
