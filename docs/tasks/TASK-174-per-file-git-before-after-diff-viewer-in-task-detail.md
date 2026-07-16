---
id: TASK-174
title: "Per-file git before/after diff viewer in task detail"
swimlane: core
kind: feature
epic: agent-hub
labels: [ready]
status: archive
priority: P2
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260605-183120-db30
depends_on: []
blocked_by: []
references: []
---
# TASK-174: Per-file git before/after diff viewer in task detail

**Outcome (one sentence):** From a task's commit list, a user can expand a commit to its changed files and click any file to see its git before/after unified diff in a popup, served by new sandboxed read-only endpoints.

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/core/web/routes/board.py
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a task whose work was committed (task .md committed with the code)
- **When** the user expands a commit and clicks a changed file
- **Then** a popup shows that file's unified diff (added/removed lines) for that commit; sha is format-validated and file paths are sandboxed to the repo; endpoints fail-open with the envelope; board route tests + make ui-build green.

## Work Log
- 2026-06-06 [claude]: Added read-only sandboxed GET /api/board/commit/{sha} (numstat file list) + GET /api/board/diff?sha=&file= (unified per-
