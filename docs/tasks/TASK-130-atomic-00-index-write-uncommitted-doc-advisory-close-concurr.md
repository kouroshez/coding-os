---
id: TASK-130
title: "Atomic 00-index write + uncommitted-doc advisory — close concurrent-corruption + drift windows"
swimlane: core
kind: bug
epic: doc-system
labels: [docs-system, concurrency, nav, audit-d5-f8, ready]
status: complete
priority: P2
appetite: "1d"
created: 2026-06-05
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260527-151803-0b9f
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
1. Generate a 00-index in a fresh dir with no existing index: `python src/scripts/regen_doc_index.py <dir> --dry-run`.
2. End a session with uncommitted `docs/**/*.md` edits.
Expected: the generated body carries a `> Nav:` breadcrumb; session end surfaces an uncommitted-doc advisory.
Actual (pre-fix): no `> Nav:` line in the generated body; no Stop/SessionEnd advisory (only a SessionStart dirty-tree notice existed).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** regen_doc_index.py generates a 00-index and the Stop hook runs at session end
- **When** a first-time 00-index is generated AND the session ends with uncommitted docs
- **Then** the write is atomic (tmp + os.replace, D5-F8/D7-F2), the first-time body emits a `> Nav: [Docs Index](../00-index.md)` breadcrumb (D1-F5), headers are sorted deterministically before truncation (D1-F8), and session-end.sh prints a one-line advisory naming the count of uncommitted `docs/` files (D5-F11); `make verify-hooks` clean.

## Work Log
- 2026-06-06 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-06 [claude]: committed 40a7b150: src/core/hooks/session-end.sh, src/scripts/regen_doc_index.py
