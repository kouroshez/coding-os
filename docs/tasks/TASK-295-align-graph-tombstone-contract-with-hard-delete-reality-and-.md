---
id: TASK-295
title: "Align graph tombstone contract with hard-delete reality and audit-log node deletions"
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
# TASK-295: Align graph tombstone contract with hard-delete reality and audit-log node deletions

**Outcome (one sentence):** The graph-os-authoring skill claimed removed symbols are tombstoned (deleted_at, 90d compaction) but delete_nodes_for_file hard-deletes with no deleted_at column; for a HEAD-of-tree code graph hard-delete is correct, so align the docs to reality with a written rationale and add a proportionate forensic trail.

## Read First
- src/core/graph_os/backends/sqlite_backend.py
- src/templates/meta/skills/graph-os-authoring/SKILL.md
- docs/engineering/graph_os-queries.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the graph-os-authoring SSOT claimed tombstoning, **When** the doc is updated, **Then** it states hard-delete is the contract for a HEAD-of-tree graph (git is the forensic record), with rationale, and no text claims deleted_at/tombstone/90d-compaction — verified by a test (`test_skill_doc_matches_hard_delete_reality`).
- **Given** a file's nodes are deleted on reindex, **When** delete_nodes_for_file runs, **Then** the deletion is recorded for forensics. DECISION (Rule 22 + memory-policy): a per-delete **audit_log DB row** was rejected — delete_nodes_for_file runs on every incremental reindex (hot path), so a DB row per call would flood the audit table with routine churn (anti-pattern). Forensics is instead a fail-open `logger.debug("hard-deleted N nodes for <path>")`; git remains the authoritative record of what existed.
- **Then** tests assert hard-delete behavior + absence of a deleted_at column (`test_delete_nodes_for_file_hard_deletes`, `test_graph_nodes_has_no_deleted_at_column`); graph_os matrix green (986 passed).

## Work Log
- 2026-06-09 [claude]: Diverged from the draft "audit_log DB row" acceptance — that path floods the audit table on every reindex. Chose logger.debug forensics + doc alignment instead (honest, Rule 22). Skill SSOT + rendered .claude copy updated; 3 hard-delete tests added.
