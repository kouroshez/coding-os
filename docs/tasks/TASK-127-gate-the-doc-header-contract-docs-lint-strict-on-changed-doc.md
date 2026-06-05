---
id: TASK-127
title: "Gate the doc header contract — docs-lint strict on changed docs in CI + pre-commit batch + freeform-create WARN hook"
swimlane: core
kind: feature
epic: doc-system
labels: [docs-system, enforcement, ssot, audit-d5-f1, ready]
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

# TASK-127: Gate the doc header contract — docs-lint strict on changed docs in CI + pre-commit batch + freeform-create WARN hook

**Outcome (one sentence):** The header+taxonomy contract docs-system.md advertises is actually enforced where docs are produced: (1) CI runs docs-lint in strict mode on git-changed docs only (D5-F1), (2) the git pre-commit batch gains a doc-header check for changed docs/**/*.md (D5-F7), (3) a PreToolUse Write WARN fires when a new freeform doc lacks a valid header, pointing at doc-cheat-sheet (D5-F4). Legacy backlog stays advisory; only new/changed docs gate.

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- src/core/scripts/docs-lint.sh
- src/core/hooks/_helpers/pre_commit_batch.py
- src/core/hooks/enforce-template.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
