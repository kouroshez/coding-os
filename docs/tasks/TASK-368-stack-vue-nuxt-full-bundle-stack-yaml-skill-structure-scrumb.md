---
id: TASK-368
title: "Stack: vue-nuxt \u2014 full bundle (stack.yaml, skill, structure, scrumban, playbook, rules, verify, golden)"
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
depends_on: [TASK-361]
blocked_by: []
references: []
---

# TASK-368: Stack: vue-nuxt — full bundle (stack.yaml, skill, structure, scrumban, playbook, rules, verify, golden)

**Outcome (one sentence):** A complete vue-nuxt stack (language=typescript) passes the bundle lint with a new vue-nuxt skill, structure spec (app/ pages/ components/ composables/), frontend swimlanes, frontend-ui playbook + engineering rules, verify row and golden test — proving the factory on a frontend stack.

## Read First
- docs/playbooks/template-authoring.md
- src/templates/nextjs/stack.yaml
- src/templates/nextjs/skills/nextjs-react/SKILL.md
- tests/test_template_scaffold.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the factory lint, **When** run against vue-nuxt, **Then** all bundle artifacts pass including a schema-valid vue-nuxt skill written to the public skill standard (frontmatter tiers, globs on src/frontend/**).
- **Given** `cos init --template vue-nuxt --yes`, **When** scaffolded, **Then** the tree matches the declared Nuxt structure, swimlanes mirror the nextjs frontend set adapted to Nuxt, and the scaffold passes nuxi typecheck on the fixture.
- **Given** regen, **When** `make regen-rules` runs, **Then** vue-nuxt rows appear in both derived registries with zero hand edits.
- **Given** the matrix, **When** `uv run pytest tests/test_template_scaffold.py -q` runs, **Then** green including the new golden.

## Work Log
