---
id: TASK-371
title: "Preset catalog v1 \u2014 five world presets (AI-SaaS, T3-style, PERN, Django+Next, RN+API)"
swimlane: templates
kind: feature
epic: D-catalog
labels: [wave-4, onboarding-program, ready]
status: testing
priority: P2
appetite: 1d
created: 2026-06-11
started: 2026-06-11
completed: null
agent_session: ses-claude-20260610-185418-2b3f
depends_on: [TASK-356, TASK-367, TASK-368]
blocked_by: []
references: []
---
# TASK-371: Preset catalog v1 — five world presets (AI-SaaS, T3-style, PERN, Django+Next, RN+API)

**Outcome (one sentence):** Five curated preset.yaml files composed only from installed stacks (AI-SaaS = fastapi+nextjs, T3-style = nextjs+typescript, PERN = node-express+react, Django+Next, RN+fastapi backend) each scaffold green via wizard and CLI and appear in the onboarding preset step with descriptions.

## Read First
- src/templates/
- src/cli/main.py
- docs/playbooks/template-authoring.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the five preset files, **When** preset discovery loads, **Then** each is schema-valid with label, description, stacks, default modules/skills and shows in both CLI discovery and the wizard preset step.
- **Given** each preset, **When** `cos init --preset <id> --yes` runs in a temp dir, **Then** scaffold completes green with union-merged configs and the anatomy contract respected (one scripted test iterating all five).
- **Given** a preset referencing a missing stack, **When** discovery loads, **Then** it is excluded with a logged reason (no crash, no silent half-render).
- **Given** the matrix, **When** `uv run pytest tests/test_cli.py tests/test_template_scaffold.py -q` runs, **Then** green.

## Work Log
