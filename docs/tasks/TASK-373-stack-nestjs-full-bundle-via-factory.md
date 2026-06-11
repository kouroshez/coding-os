---
id: TASK-373
title: "Stack: nestjs \u2014 full bundle via factory"
swimlane: templates
kind: feature
epic: D-catalog
labels: [backlog, onboarding-program, ready]
status: icebox
priority: P2
appetite: 2d
created: 2026-06-11
started: null
completed: null
agent_session: null
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
