---
id: TASK-373
title: "Stack: nestjs \u2014 full bundle via factory"
swimlane: templates
kind: feature
epic: D-catalog
labels: [backlog, onboarding-program, ready]
status: archive
priority: P2
appetite: 2d
created: 2026-06-11
started: 2026-06-14
completed: 2026-06-14
agent_session: ses-claude-20260614-003127-9cfa
depends_on: [TASK-361]
blocked_by: []
references: []
---
# TASK-373: Stack: nestjs — full bundle via factory

**Outcome (one sentence):** Complete nestjs stack bundle (stack.yaml language=typescript, nestjs skill, structure, scrumban, playbook, rules, verify row, golden test) passing the factory lint.

## Read First
- docs/playbooks/template-authoring.md
- src/templates/fastapi/stack.yaml (closest backend-category shape)
- docs/engineering/project-anatomy.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the factory contract (TASK-361 checklist), **When** `cos init --template nestjs --yes --no-index --no-register` runs in a sandbox, **Then** the scaffold lands under structure.root `src/backend` with placeholders resolved and scaffold-boundary.yaml aggregated.
- **Given** stack.yaml (language=typescript, category=backend), **When** schema validation + `make regen-rules` run, **Then** stack.schema.json validates and dimension-registry/skill-enforcement gain the nestjs rows with zero hand-edits.
- **Given** the new nestjs SKILL.md, **When** the skill registry loads, **Then** frontmatter is schema-valid (tier/domain enums) with no warnings.
- **Given** the matrix, **When** `uv run pytest tests/test_template_scaffold.py tests/test_anatomy_contract.py -q` runs, **Then** green including the golden fixture for the new stack.

## Work Log
- 2026-06-14 [claude]: Edit stack.yaml
- 2026-06-14 [claude]: Edit scaffold-boundary.yaml
- 2026-06-14 [claude]: Edit scrumban-config.yaml
- 2026-06-14 [claude]: Edit package.json
- 2026-06-14 [claude]: Edit tsconfig.json
- 2026-06-14 [claude]: Edit nest-cli.json
- 2026-06-14 [claude]: Edit nestjs-service.md
- 2026-06-14 [claude]: Edit nestjs-rules.md
- 2026-06-14 [claude]: Edit SKILL.md
- 2026-06-14 [claude]: Edit main.ts
- 2026-06-14 [claude]: Edit app.module.ts
- 2026-06-14 [claude]: Edit all-exceptions.filter.ts
- 2026-06-14 [claude]: Edit health.module.ts
- 2026-06-14 [claude]: Edit health.controller.ts
- 2026-06-14 [claude]: Edit health.service.ts
- 2026-06-14 [claude]: Authored nestjs stack bundle (stack.yaml language=typescript/backend, nestjs SKILL.md, scaffold: main/app.module + healt
- 2026-06-14 [claude]: committed 839a010e: src/core/rules/dimension-registry.md, src/core/rules/skill-enforcement.md, src/core/scaffold_manifes
