---
id: TASK-295
title: "Align graph tombstone contract with hard-delete reality (no node-deletion ledger)"
swimlane: core
kind: refactor
epic: graph-coverage-hardening
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260608-203030-6c0f
depends_on: []
blocked_by: []
references: []
---

# TASK-295: Align graph tombstone contract with hard-delete reality (no node-deletion ledger)

**Outcome (one sentence):** The graph-os-authoring skill claimed removed symbols are tombstoned (deleted_at, 90d compaction) but delete_nodes_for_file hard-deletes with no deleted_at column; for a HEAD-of-tree code graph hard-delete is correct, so align the docs to reality with a written rationale and keep the deletion trail proportionate.

## Read First
- src/core/graph_os/backends/sqlite_backend.py
- src/templates/meta/skills/graph-os-authoring/SKILL.md
- docs/engineering/graph_os-queries.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the graph-os-authoring SSOT claimed tombstoning, **When** the doc is updated, **Then** it states hard-delete is the contract for a HEAD-of-tree graph (git is the record), with rationale, and no text claims deleted_at/tombstone/90d-compaction — verified by `test_skill_doc_matches_hard_delete_reality`.
- **Given** node prune runs on every per-file reindex, **When** delete_nodes_for_file runs, **Then** it keeps NO deletion ledger of its own. DECISION (Rule 22 + memory-policy): a per-prune DB row would be pure churn. The only deletion audit in the system is the doc_audit_trail row prune_deleted_path writes for a rare whole-.md-file delete (doc-scoped, not this hot path). Node prune is a fail-open `logger.debug`; git is the authoritative record. NOTE: this is distinct from the governance "exhaustive-intent audit" layer, which was removed entirely (task is enough) — no reference to it here.
- **Then** tests assert hard-delete + absence of a deleted_at column (`test_delete_nodes_for_file_hard_deletes`, `test_graph_nodes_has_no_deleted_at_column`); graph_os matrix green.

## Work Log
- 2026-06-09 [claude]: Diverged from the draft "audit row on delete" acceptance — node prune is a per-reindex hot path; chose logger.debug + doc alignment (Rule 22). Skill SSOT + rendered .claude copy updated; 3 hard-delete tests.
- 2026-06-09 [claude]: Corrected imprecise "audit_log table" wording in skill/backend/task — the real deletion audit is doc_audit_trail (doc-scoped, via prune_deleted_path); the graph keeps no node-deletion ledger. Distinct from the removed exhaustive-intent governance audit.
