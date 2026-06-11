---
id: TASK-359
title: "CLI parity for onboarding + official agent-driven init recipe"
swimlane: cli
kind: feature
epic: B-onboarding
labels: [wave-2, onboarding-program, ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-06-11
started: 2026-06-11
completed: null
agent_session: ses-claude-20260610-185418-2b3f
depends_on: [TASK-356]
blocked_by: []
references: []
---
# TASK-359: CLI parity for onboarding + official agent-driven init recipe

**Outcome (one sentence):** `cos init` gains --preset/--skills/--summary/--swimlanes flags mirroring every wizard option; non-TTY runs fail fast with explicit errors instead of returning None; an official agent recipe (command/skill) documents the one-shot non-interactive init form.

## Read First
- src/cli/main.py
- src/cli/_init_helpers.py
- src/core/commands/
- docs/playbooks/template-authoring.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** any composition expressible in the wizard, **When** the equivalent `cos init` flag form runs with --yes, **Then** the resulting project is identical (same scaffold diff) to the wizard output — parity proven by a fixture test.
- **Given** a non-TTY environment missing required inputs, **When** `cos init` runs without --yes, **Then** it exits non-zero immediately with a message naming the missing flags (no silent None path).
- **Given** the agent recipe, **When** an agent follows it verbatim, **Then** a single command produces a green init including preset, skills and summary.
- **Given** the matrix, **When** `uv run pytest tests/test_cli.py -q` runs, **Then** green with parity + non-TTY tests.

## Work Log
