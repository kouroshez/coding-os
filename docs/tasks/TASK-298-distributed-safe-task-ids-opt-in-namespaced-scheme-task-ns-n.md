---
id: TASK-298
title: "Distributed-safe task IDs: opt-in namespaced scheme (TASK-NS-NNN) to end multi-contributor id collisions"
swimlane: core
kind: feature
epic: panel-state-isolation
labels: [scrumban, distributed, ids, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260609-151118-a8c3
depends_on: []
blocked_by: []
references: []
---
# TASK-298: Distributed-safe task IDs: opt-in namespaced scheme (TASK-NS-NNN) to end multi-contributor id collisions

**Outcome (one sentence):** Multi-contributor projects can opt into a per-contributor namespaced task-id scheme (TASK-NS-NNN, prefix from config or git email) so two un-synced contributors never collide; single-owner projects keep TASK-NNN unchanged.

## Read First
- src/core/board_os/mcp_tools.py
- src/core/board_os/parser.py
- src/core/hooks/cos-env.sh
- docs/governance/task-lifecycle.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** task_id_scheme=sequential (default), **When** a task is created, **Then** the id is TASK-NNN exactly as today (zero change for single-owner projects).
- **Given** task_id_scheme=namespaced, **When** a task is created, **Then** the id is TASK-<NS>-NNN where NS is the configured prefix or derived from git user.email, and NNN is max+1 WITHIN that namespace.
- **Given** two contributors with prefixes KO and JD un-synced, **When** both create their 280th task, **Then** they are TASK-KO-280 and TASK-JD-280 — distinct, no collision at PR/merge.
- **Given** a namespaced id, **When** any task-id-aware site runs (parser, frontmatter validation, .task-current extraction, commit-linking, git log --grep), **Then** it recognises TASK-<NS>-NNN via the broadened canonical regex, while TASK-NNN still matches (backward-compatible).
- **Given** the change, **When** docs are read, **Then** task-lifecycle.md documents the scheme + config keys.

## Read First (extra)
- src/core/hooks/cos-env.sh (shell task-id helper)
- src/scripts/_prepare_commit_msg_body.sh / link-commit-to-task.sh (id extraction)

## Work Log
- 2026-06-09 [claude]: Shipped opt-in per-contributor namespaced task ids. config.py: task_id_scheme (sequential|namespaced) + task_id_prefix (
