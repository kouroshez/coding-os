---
id: TASK-349
title: "subsystems.yaml \u2014 module registry with kernel/optional split + state API"
swimlane: core
kind: feature
epic: G-modularity
labels: [wave-3, onboarding-program, ready]
status: testing
priority: P0
appetite: 2d
created: 2026-06-11
started: 2026-06-11
completed: null
agent_session: ses-claude-20260610-185418-2b3f
depends_on: []
blocked_by: []
references: []
---
# TASK-349: subsystems.yaml — module registry with kernel/optional split + state API

**Outcome (one sentence):** Data-driven src/core/subsystems.yaml declares toggleable modules (docs, tasks/board, graph, memory, hub-extras) with dependency declarations; loader API + per-project toggle state in $COS_STATE_DIR; safety hooks and kernel non-disableable by construction (extends TASK-256 override layer).

## Read First
- src/cli/project_overrides.py
- src/core/hooks/cos-env.sh
- src/core/hooks/registry.yaml
- docs/governance/critical-rules.md
- docs/engineering/state-files.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** subsystems.yaml, **When** the loader parses it, **Then** each module exposes id, label, owned hooks/rules/tools/doc-tags and depends_on, and a module marked kernel (safety/state) cannot be disabled (attempt returns a refusal naming the module).
- **Given** a module with unmet dependencies (disable docs while tasks requires it — per declared graph), **When** a toggle is attempted, **Then** the API refuses with the dependency chain spelled out.
- **Given** a consumer project with no subsystems state file, **When** any reader queries module state, **Then** all modules default to enabled (backward compatible) and the state file is created lazily in $COS_STATE_DIR.
- **Given** the verification matrix, **When** `uv run pytest tests/test_cli.py -q` runs, **Then** loader/refusal/default-on tests pass and the suite is green.

## Work Log
