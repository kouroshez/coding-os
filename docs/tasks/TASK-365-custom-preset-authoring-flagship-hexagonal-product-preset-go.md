---
id: TASK-365
title: "Custom preset authoring + flagship hexagonal-product preset (Go core / go-fiber API / FastAPI AI / RN)"
swimlane: templates
kind: feature
epic: D-catalog
labels: [wave-4, onboarding-program, ready]
status: archive
priority: P1
appetite: 2d
created: 2026-06-11
started: 2026-06-11
completed: 2026-06-11
agent_session: ses-claude-20260610-185418-2b3f
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
- 2026-06-11 [claude]: Edit preset_registry.py
- 2026-06-11 [claude]: Edit preset_registry.py
- 2026-06-11 [claude]: Edit preset_registry.py
- 2026-06-11 [claude]: Edit preset_commands.py
- 2026-06-11 [claude]: Edit hexagonal-product.yaml
- 2026-06-11 [claude]: commit 76ad8897da — feat(templates): flagship hexagonal preset + cos preset authoring (TASK-365)
- 2026-06-11 [claude]: IMPL DONE (parked, batch 6 #2) — cos preset list/create/export/import with ~/.coding-os/presets ($COS_USER_PRESETS_DIR)
- 2026-06-11 [claude]: CLOSED on batch-6 suite: test_cli + test_template_scaffold 169 passed (28m36s). Commit 76ad8897. Self-score 9.5/10: the 
