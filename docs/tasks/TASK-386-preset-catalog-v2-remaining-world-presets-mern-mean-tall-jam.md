---
id: TASK-386
title: "Preset catalog v2 \u2014 remaining world presets (MERN, MEAN, TALL, JAMstack, Flutter+BaaS, \u2026)"
swimlane: templates
kind: feature
epic: D-catalog
labels: [backlog, onboarding-program, ready]
status: complete
priority: P3
appetite: 2d
created: 2026-06-11
started: 2026-06-14
completed: 2026-06-14
agent_session: ses-claude-20260614-003127-9cfa
depends_on: [TASK-373, TASK-374, TASK-375, TASK-376, TASK-377, TASK-378, TASK-379, TASK-380, TASK-381, TASK-382, TASK-383]
blocked_by: []
references: []
---
# TASK-386: Preset catalog v2 — remaining world presets (MERN, MEAN, TALL, JAMstack, Flutter+BaaS, …)

**Outcome (one sentence):** Remaining world presets composed from the grown stack catalog (MERN/MEAN need their stacks first); each scaffolds green and appears in onboarding with descriptions.

## Read First
- src/templates/_presets/ (TASK-356 model)
- src/cli/preset_registry.py
- docs/engineering/config-composition.md § Presets

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the stacks shipped by the D-catalog tasks (373–383), **When** each new `_presets/<id>.yaml` is added, **Then** `load_preset_registry` validates it against the live stack registry (a preset whose stacks are not yet shipped stays out of this task's scope — depends_on the stack task).
- **Given** each preset, **When** `cos init --preset <id> --dry-config` runs, **Then** the merged config preview succeeds with every conflict reported (none silent).
- **Given** discovery, **When** `cos list-stacks --format json` and `GET /api/hub/presets` run, **Then** every new preset is listed with a non-empty description.
- **Given** the matrix, **When** `uv run pytest tests/test_cli.py::TestPresets -q` (extended) runs, **Then** green.

## Work Log
- 2026-06-14 [claude]: Status transitioned to complete via cos task-done.
