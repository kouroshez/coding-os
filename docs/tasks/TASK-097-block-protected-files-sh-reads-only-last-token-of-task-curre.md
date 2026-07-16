---
id: TASK-097
title: "block-protected-files.sh reads only last token of .task-current — governance marker false-block"
swimlane: core
kind: bug
epic: null
labels: [hooks, governance, regression, ready]
status: archive
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
# TASK-097: block-protected-files.sh reads only last token of .task-current — governance marker false-block

**Outcome (one sentence):** A multi-word governance marker (e.g. 'docs-update TASK-096 align-docs') correctly allows governance edits; the hook matches the whole value-after-session-id, not just the last whitespace token.

## Read First
- src/core/hooks/block-protected-files.sh

## Repro Steps
1. `write-state.sh .task-current "docs-update TASK-096 align-docs"` (multi-word value).
2. Edit AGENTS.md (or any governance path) so block-protected-files.sh fires.
Expected: allowed — the active task is a docs-update task.
Actual: BLOCKED — `${TASK_VALUE##* }` extracts only "align-docs" (last token), which doesn't match `*docs-update*`.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `.task-current` = `<sid> docs-update TASK-096 align-docs` (keyword not the last token)
- **When** block-protected-files.sh evaluates the governance allow-case (both the scaffold branch and the general branch)
- **Then** the edit is allowed (it matches the value-after-session-id via `${TASK_VALUE#* }`), while a non-governance marker (`<sid> TASK-100-feature`) is still BLOCKED.

## Work Log
- 2026-06-04 [claude]: Fixed both sites in block-protected-files.sh: ${TASK_VALUE##* } (last token) → ${TASK_VALUE#* } (value after session-id)
