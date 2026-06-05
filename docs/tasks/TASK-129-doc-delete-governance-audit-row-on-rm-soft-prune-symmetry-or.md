---
id: TASK-129
title: "Doc-delete governance — audit row on rm + soft-prune symmetry + orphan-chunk reconciliation + read_error prune fix"
swimlane: core
kind: bug
epic: doc-system
labels: [docs-system, enforcement, audit-trail, audit-d5-f2, ready]
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

# TASK-129: Doc-delete governance — audit row on rm + soft-prune symmetry + orphan-chunk reconciliation + read_error prune fix

**Outcome (one sentence):** Deleting a doc is no longer a silent, unaudited hard-erase: the rm-prune path writes an action='deleted' doc_audit_trail row (D5-F2); prune heuristic gains a cos doctor reconciliation sweep for orphaned RAG chunks whose path the tokenizer missed (D5-F9); capture-audit drops get a periodic CI reconciliation vs git log (D5-F10); and reindex_dispatch's read_error short-circuit no longer skips delete_nodes_for_file prune (D7-F1 partial).

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- src/core/hooks/auto-prune-deleted-files.sh
- src/core/hooks/_helpers/prune_deleted_path.py
- src/core/graph_os/tools/reindex_dispatch.py

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
