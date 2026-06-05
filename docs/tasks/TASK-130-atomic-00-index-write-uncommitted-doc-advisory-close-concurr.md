---
id: TASK-130
title: "Atomic 00-index write + uncommitted-doc advisory — close concurrent-corruption + drift windows"
swimlane: core
kind: bug
epic: doc-system
labels: [docs-system, concurrency, nav, audit-d5-f8, ready]
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

# TASK-130: Atomic 00-index write + uncommitted-doc advisory — close concurrent-corruption + drift windows

**Outcome (one sentence):** regen_doc_index.py writes atomically (tmp + os.replace) so concurrent agents in the same docs dir cannot tear/clobber the 00-index (D5-F8, D7-F2); the generator also emits the > Nav: line its own rules require (D1-F5) and sorts deterministically before truncating (D1-F8); and a Stop/SessionEnd advisory surfaces uncommitted doc edits so the audit trail can't record truth the repo never saw (D5-F11).

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- src/scripts/regen_doc_index.py
- src/core/hooks/auto-regen-doc-index.sh

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
