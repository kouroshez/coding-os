---
id: TASK-365
title: "Custom preset authoring + flagship hexagonal-product preset (Go core / go-fiber API / FastAPI AI / RN)"
swimlane: templates
kind: feature
epic: D-catalog
labels: [wave-4, onboarding-program, ready]
status: icebox
priority: P1
appetite: 2d
created: 2026-06-11
started: null
completed: null
agent_session: null
depends_on: [TASK-356, TASK-361]
blocked_by: []
references: []
---

# TASK-365: Custom preset authoring + flagship hexagonal-product preset (Go core / go-fiber API / FastAPI AI / RN)

**Outcome (one sentence):** `cos preset create/export` lets a user save a custom composition; the flagship hexagonal-product preset (Go business core + go-fiber API + FastAPI AI adapter + React Native app under src/services anatomy) scaffolds green end-to-end via both wizard and CLI — first real multi-service dogfood.

## Read First
- src/templates/go-fiber/stack.yaml
- src/templates/fastapi/stack.yaml
- src/templates/react-native/stack.yaml
- src/core/skills/hexagonal-architecture/SKILL.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an interactive or flag-driven composition, **When** `cos preset create` runs, **Then** a schema-valid preset.yaml lands in the user preset dir, appears in discovery, and `cos preset export` emits a shareable file that re-imports cleanly.
- **Given** the hexagonal-product preset, **When** scaffolded via CLI with --yes, **Then** the tree contains src/services/{core,api,ai} + src/mobile + src/shared/contracts per the anatomy contract, all boundary/skill-enforcement globs resolve per service, and the scaffold golden test passes.
- **Given** the same preset via the wizard, **When** created, **Then** the result diff vs CLI output is empty (parity).
- **Given** the matrix, **When** `uv run pytest tests/test_cli.py tests/test_template_scaffold.py -q` runs, **Then** green.

## Work Log
