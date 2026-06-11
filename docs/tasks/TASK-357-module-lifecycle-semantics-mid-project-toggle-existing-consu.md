---
id: TASK-357
title: "Module lifecycle semantics \u2014 mid-project toggle + existing-consumer migration"
swimlane: core
kind: feature
epic: G-modularity
labels: [wave-3, onboarding-program, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-06-11
started: null
completed: null
agent_session: null
depends_on: [TASK-353, TASK-354]
blocked_by: []
references: []
---

# TASK-357: Module lifecycle semantics — mid-project toggle + existing-consumer migration

**Outcome (one sentence):** Disabling a module mid-project gates its tools/hooks but preserves all data (docs/tasks/graph index); re-enable restores cleanly; `cos update` migrates existing consumer projects to the module registry with default-all-on and zero behavior change.

## Read First
- src/cli/update.py
- src/cli/project_overrides.py
- docs/engineering/state-files.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a project with 10 board tasks, **When** the tasks module is disabled then re-enabled, **Then** no task file or DB row is deleted and the board renders identically after re-enable (data-preservation test).
- **Given** a pre-module consumer project, **When** `cos update` runs, **Then** it gains the module state file with all modules on and a diff of rendered artifacts is empty (zero behavior change proven by golden comparison).
- **Given** a disabled module's residual artifacts (AGENTS.md sections, hook links), **When** the toggle completes, **Then** regen has removed/restored them atomically — no half state on failure (rollback covered by test).
- **Given** the matrix, **When** `uv run pytest tests/test_cli.py -q` runs, **Then** green.

## Work Log
