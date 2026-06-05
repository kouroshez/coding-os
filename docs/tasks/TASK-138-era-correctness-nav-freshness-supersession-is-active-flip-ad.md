---
id: TASK-138
title: "Era-correctness + nav freshness — supersession is_active flip + add-stack nav regen + cheat-sheet target dirs at scaffold"
swimlane: thinking_os
kind: bug
epic: doc-system
labels: [docs-system, rag, era-correctness, audit-d7-f9, ready]
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

# TASK-138: Era-correctness + nav freshness — supersession is_active flip + add-stack nav regen + cheat-sheet target dirs at scaffold

**Outcome (one sentence):** Superseded specs stop being served as current: a superseded_by/supersedes frontmatter field flips is_active on re-index so cos_doc_search hides the old era by default (D7-F9); cos add-stack re-renders docs/00-index.md + foundation-map.md (not just AGENTS.md) so the master nav doesn't freeze at base-only (D6-F4); and the doc-cheat-sheet's 5 target dirs are scaffolded (.gitkeep + stub 00-index) so create-time routing lands somewhere real (D6-F5).

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- src/core/thinking_os/doc_indexer.py
- src/cli/add_stack.py
- docs/governance/_templates/doc-cheat-sheet.md

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
