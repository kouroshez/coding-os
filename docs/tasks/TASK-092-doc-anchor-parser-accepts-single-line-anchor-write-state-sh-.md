---
id: TASK-092
title: "doc-anchor parser accepts single-line anchor (write-state.sh compatibility)"
swimlane: core
kind: bug
epic: null
labels: [hooks, doc-anchor, robustness, ready]
status: complete
priority: P2
appetite: "1d"
created: 2026-06-04
started: 2026-06-04
completed: 2026-06-04
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-092: doc-anchor parser accepts single-line anchor (write-state.sh compatibility)

**Outcome (one sentence):** enforce-doc-anchor.sh accepts a one-line anchor whose header carries `task:TASK-NNN` + inline ref (the form write-state.sh writes), not only the multi-line cos-task-start form, so agents stop getting false BLOCKs.

## Read First
- src/core/hooks/enforce-doc-anchor.sh
- src/core/hooks/write-state.sh

## Repro Steps
1. Run `write-state.sh .doc-anchor "task:TASK-NNN <doc-ref>"` (single line — what an agent does as the fallback when cos-task-start's panel routing is awkward).
2. Attempt a code Write/Edit so enforce-doc-anchor.sh fires.
Expected: the anchor (which names a task + a doc ref) is accepted.
Actual: BLOCKED "Doc anchor is empty for this session" — the session-aware branch reads content only from line 2+, so a one-line anchor looks empty.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a `.doc-anchor` whose single line is `ses-… task:TASK-NNN <ref>`
- **When** enforce-doc-anchor.sh evaluates it for a code edit
- **Then** it passes (the header's `task:<id> <ref>` counts as anchor content), while a header with no task id or a placeholder ref is still BLOCKED. Multi-line cos-task-start anchors keep working.

## Work Log
- 2026-06-04 [claude]: enforce-doc-anchor.sh now requires task:<id> in the header and folds the header ref into the content check, so a one-lin
