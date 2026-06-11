---
id: TASK-138
title: "Era-correctness + nav freshness \u2014 supersession is_active flip + add-stack nav regen + cheat-sheet target dirs at scaffold"
swimlane: "thinking_os"
kind: bug
epic: doc-system
labels: [docs-system, rag, era-correctness, audit-d7-f9, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-05
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-138: Era-correctness + nav freshness — supersession is_active flip + add-stack nav regen + cheat-sheet target dirs at scaffold

**Outcome (one sentence):** Superseded specs stop being served as current — a `superseded_by` frontmatter key flips is_active=0 on (re)index so cos_doc_search hides the old era by default (D7-F9); and the doc-cheat-sheet's create-time routing targets exist in the base scaffold so a new doc lands somewhere real (D6-F5). (D6-F4 add-stack nav regen of 00-index/foundation-map is deferred — it needs a dedicated stack-aware index renderer, substantial new code beyond this era-correctness fix.)

## Read First
- src/core/thinking_os/doc_indexer.py
- src/templates/_base/scaffold/docs/

## Repro Steps
1. Add `superseded_by:docs/...` to a doc's header and re-index; the doc still indexes is_active=1 (line 529/753 hardcoded), so cos_doc_search keeps serving the superseded era.
2. The doc-cheat-sheet routes new docs to docs/playbooks/, docs/engineering/, docs/ops/runbooks/ — none of which exist in the base scaffold.
Expected: superseded docs index inactive; the cheat-sheet's routing targets exist at scaffold time.
Actual: is_active hardcoded to 1; routing target dirs missing.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a doc whose header declares superseded_by, and a freshly scaffolded base project
- **When** the doc indexer runs / a contributor follows the doc-cheat-sheet routing
- **Then** the superseded doc's chunks are is_active=0 (current docs stay 1), guarded by a test; and docs/playbooks/, docs/engineering/, docs/ops/runbooks/ exist as stub indexes in the base scaffold — verified by test-thinking_os + docs-lint.

## Work Log
- 2026-06-07 [claude]: D7-F9: doc_indexer now flips is_active=0 when a doc header declares superseded_by (both insert sites; superseded_by is a
- 2026-06-07 [claude]: committed 37f90663: src/core/thinking_os/doc_indexer.py, src/core/thinking_os/tests/test_doc_indexer.py, src/templates/_
