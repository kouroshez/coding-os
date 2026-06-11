---
id: TASK-367
title: "Stack: node-express \u2014 full bundle (stack.yaml, skill, structure, scrumban, playbook, rules, verify, golden)"
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

# TASK-367: Stack: node-express — full bundle (stack.yaml, skill, structure, scrumban, playbook, rules, verify, golden)

**Outcome (one sentence):** A complete node-express stack (language=typescript, extends typescript-plain) passes the bundle lint: stack skill (express patterns, reuses core node-backend), structure spec, scrumban swimlanes, backend-api playbook + engineering rules, verify-matrix row, golden scaffold test — proving the factory on the world's most-used backend.

## Read First
- docs/playbooks/template-authoring.md
- src/templates/go-fiber/stack.yaml
- src/core/skills/node-backend/SKILL.md
- tests/test_template_scaffold.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the factory lint from TASK-361, **When** run against node-express, **Then** every bundle artifact passes (stack.yaml with language+structure, node-express skill with schema-valid frontmatter, scrumban-config, playbook, engineering-rules, verify row, golden test).
- **Given** `cos init --template node-express --yes`, **When** scaffolded, **Then** the project tree matches the declared structure (src/backend with routes/middleware/services per spec), skill-enforcement globs route edits to the node-express skill, and the scaffold compiles (tsc --noEmit on the scaffold fixture).
- **Given** regen, **When** `make regen-rules` runs, **Then** dimension-registry and skill-enforcement include node-express rows with no hand edits.
- **Given** the matrix, **When** `uv run pytest tests/test_template_scaffold.py -q` runs, **Then** green including the new golden.

## Work Log
