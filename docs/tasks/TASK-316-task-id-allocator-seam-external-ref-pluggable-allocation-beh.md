---
id: TASK-316
title: "Task-id allocator seam + external_ref: pluggable allocation behind a stable id format, optional issue linking"
swimlane: core
kind: feature
epic: panel-state-isolation
labels: [ids, architecture, distributed, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-10
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260609-151118-a8c3
depends_on: []
blocked_by: []
references: []
---
# TASK-316: Task-id allocator seam + external_ref: pluggable allocation behind a stable id format, optional issue linking

**Outcome (one sentence):** _next_task_id dispatches through a TaskIdAllocator seam (local + namespaced behind one interface, no behavior change), and tasks carry an optional external_ref (e.g. github#42) set via cos task-link with forge auto-detection — so future allocators drop in with zero migration and issue linking never becomes the primary id.

## Read First
- src/core/board_os/mcp_tools.py
- src/core/board_os/parser.py
- docs/governance/adr-task-id-collision-resistance.md
- src/cli/board_commands.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** task_id_scheme=sequential or namespaced, **When** a task is created, **Then** _next_task_id dispatches through a TaskIdAllocator seam and the minted id is byte-identical to today (no behavior change; existing tests stay green).
- **Given** a new allocator class, **When** it is registered, **Then** it drops in behind the seam with zero change to callers or the id format.
- **Given** a task, **When** `cos task-link TASK-NNN <issue>` runs, **Then** the task gains an `external_ref` frontmatter field (e.g. github#42), forge auto-detected from `git remote`, and it is metadata only — never the primary id, never blocks creation, never needs the network at create time.
- **Given** the change, **When** the ADR is read, **Then** the seam contract + external_ref schema + forge-detection rule are documented before the code.

## Work Log
- 2026-06-10 [claude]: Shipped the allocator seam + external_ref. ADR adr-task-id-allocator-seam written first. _next_task_id refactored into a
