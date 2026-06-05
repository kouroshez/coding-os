---
id: TASK-132
title: "Resolve dead cos_audit_log_* surface — collapse to is_active + git history; fix doc-cheat-sheet dangling template refs"
swimlane: thinking_os
kind: refactor
epic: doc-system
labels: [docs-system, overengineering, audit-trail, audit-d4-f3, ready]
status: icebox
priority: P2
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: [TASK-131]
blocked_by: []
references: []
---

# TASK-132: Resolve dead cos_audit_log_* surface — collapse to is_active + git history; fix doc-cheat-sheet dangling template refs

**Outcome (one sentence):** No half-built version-history infra: collapse the unread cos_audit_log_query/timeline tools + value-less per-doc-edit auto-capture to just the is_active mechanism cos_doc_search actually uses, and serve version history via cos doc-history (D4-F3); fix the doc-cheat-sheet decision tree's references to template files that don't exist by adding the missing api-contract/adr templates or correcting the refs (D4-F5, D6-F7).

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- src/core/thinking_os/tools/audit.py
- src/core/hooks/capture-audit.sh
- docs/governance/_templates/doc-cheat-sheet.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
