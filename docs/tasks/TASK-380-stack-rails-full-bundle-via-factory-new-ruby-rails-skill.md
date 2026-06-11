---
id: TASK-380
title: "Stack: rails \u2014 full bundle via factory (new ruby/rails skill)"
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

# TASK-380: Stack: rails — full bundle via factory (new ruby/rails skill)

**Outcome (one sentence):** Complete rails stack bundle including a new ruby/rails skill (language=ruby) passing the factory lint.

## Read First
- docs/playbooks/template-authoring.md
- src/templates/django/stack.yaml (batteries-included backend shape)
- docs/engineering/project-anatomy.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the factory contract, **When** `cos init --template rails --yes --no-index --no-register` runs in a sandbox, **Then** scaffold lands under structure.root `src/backend` with placeholders resolved and the boundary aggregated.
- **Given** stack.yaml (language=ruby, category=backend), **When** schema validation + `make regen-rules` run, **Then** valid with rails skill-enforcement rows.
- **Given** the new ruby/rails SKILL.md, **When** the skill registry loads, **Then** schema-valid frontmatter with no warnings.
- **Given** the matrix, **When** `uv run pytest tests/test_template_scaffold.py tests/test_anatomy_contract.py -q` runs, **Then** green including the golden fixture.

## Work Log
