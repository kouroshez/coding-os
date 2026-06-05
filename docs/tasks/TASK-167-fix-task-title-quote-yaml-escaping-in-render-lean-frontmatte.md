---
id: TASK-167
title: "Fix task title-quote YAML escaping in _render_lean_frontmatter"
swimlane: core
kind: bug
epic: agent-hub
labels: [ready]
status: complete
priority: P1
appetite: "4h"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260605-183120-db30
depends_on: []
blocked_by: []
references: []
---
# TASK-167: Fix task title-quote YAML escaping in _render_lean_frontmatter

**Outcome (one sentence):** A task title containing a double-quote renders valid YAML and stays editable via cos_task_edit/move (route title + all string scalars through a YAML-safe quoter).

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/core/board_os/mcp_tools.py
- src/core/board_os/workflow.py

## Repro Steps
1. `cos_task_create(title='Fix "ready" gate', swimlane=core, kind=bug)`
2. `cos_task_edit` on the new task (any field).
Expected: edit succeeds, board renders the card.
Actual: `extract_frontmatter` returns None (invalid YAML from unescaped inner quotes); `cos_task_edit` fails 'not in lean frontmatter format'; status writes raise.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a task whose title contains a double-quote
- **When** it is created and then edited/moved via the semantic ops
- **Then** the frontmatter is valid YAML, `is_lean_format` is true, edit/move succeed, and a board_os unit test covers the quoted-title round-trip.

## Work Log
- 2026-06-05 [claude]: Routed all task string scalars through shared _format_yaml_scalar_token; titles with double-quotes now render valid YAML
