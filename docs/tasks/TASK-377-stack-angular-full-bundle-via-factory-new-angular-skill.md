---
id: TASK-377
title: "Stack: angular \u2014 full bundle via factory (new angular skill)"
swimlane: templates
kind: feature
epic: D-catalog
labels: [backlog, onboarding-program, ready]
status: icebox
priority: P3
appetite: 2d
created: 2026-06-11
started: null
completed: null
agent_session: null
depends_on: [TASK-361]
blocked_by: []
references: []
---

# TASK-377: Stack: angular — full bundle via factory (new angular skill)

**Outcome (one sentence):** Complete angular stack bundle including a new angular skill (language=typescript) passing the factory lint.

## Read First
- docs/playbooks/template-authoring.md
- src/templates/nextjs/stack.yaml (frontend-category shape)
- docs/engineering/project-anatomy.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the factory contract, **When** `cos init --template angular --yes --no-index --no-register` runs in a sandbox, **Then** scaffold lands under structure.root `src/frontend` with placeholders resolved and the boundary aggregated.
- **Given** stack.yaml (language=typescript, category=frontend), **When** schema validation + `make regen-rules` run, **Then** valid with angular skill-enforcement rows; composing with another frontend stack relocates per the anatomy contract.
- **Given** the new angular SKILL.md, **When** the skill registry loads, **Then** schema-valid frontmatter with no warnings.
- **Given** the matrix, **When** `uv run pytest tests/test_template_scaffold.py tests/test_anatomy_contract.py -q` runs, **Then** green including the golden fixture.

## Work Log
