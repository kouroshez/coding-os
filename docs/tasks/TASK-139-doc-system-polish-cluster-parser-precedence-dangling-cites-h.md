---
id: TASK-139
title: "Doc-system polish cluster — parser precedence, dangling cites_heading, shell-ops STATE_DIR, domain-hint regex, doc-graph-neighbor, audit naming"
swimlane: core
kind: chore
epic: doc-system
labels: [docs-system, polish, audit-d1-f7, ready]
status: icebox
priority: P3
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-139: Doc-system polish cluster — parser precedence, dangling cites_heading, shell-ops STATE_DIR, domain-hint regex, doc-graph-neighbor, audit naming

**Outcome (one sentence):** Low-severity correctness/consistency sweep: short-form opening block no longer silently overridden by long-form (D1-F7); dangling cross-file cites_heading edges reconciled (D3-F8); auto-reindex-shell-ops fallback STATE_DIR stops hardcoding .coding-os/claude for non-claude agents (D7-F10); doc-search domain-hint regex won't map swimlane to absent domains (D7-F8); add a doc-specific graph-neighbor convenience (D4-F6); document cos_doc_* vs cos_audit_log_* family boundary (D4-F7).

## Work Log
