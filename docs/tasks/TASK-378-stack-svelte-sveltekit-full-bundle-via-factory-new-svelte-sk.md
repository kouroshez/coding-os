---
id: TASK-378
title: "Stack: svelte-sveltekit \u2014 full bundle via factory (new svelte skill)"
swimlane: templates
kind: feature
epic: D-catalog
labels: [backlog, onboarding-program, ready]
status: archive
priority: P3
appetite: 2d
created: 2026-06-11
started: 2026-06-14
completed: 2026-06-14
agent_session: ses-claude-20260614-003127-9cfa
depends_on: [TASK-361]
blocked_by: []
references: []
---
# TASK-378: Stack: svelte-sveltekit — full bundle via factory (new svelte skill)

**Outcome (one sentence):** Complete svelte-sveltekit stack bundle including a new svelte skill (language=typescript) passing the factory lint.

## Read First
- docs/playbooks/template-authoring.md
- src/templates/nextjs/stack.yaml (frontend-category shape)
- docs/engineering/project-anatomy.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the factory contract, **When** `cos init --template svelte-sveltekit --yes --no-index --no-register` runs in a sandbox, **Then** scaffold lands under structure.root `src/frontend` with placeholders resolved and the boundary aggregated.
- **Given** stack.yaml (language=typescript, category=frontend), **When** schema validation + `make regen-rules` run, **Then** valid with sveltekit skill-enforcement rows.
- **Given** the new svelte SKILL.md, **When** the skill registry loads, **Then** schema-valid frontmatter with no warnings.
- **Given** the matrix, **When** `uv run pytest tests/test_template_scaffold.py tests/test_anatomy_contract.py -q` runs, **Then** green including the golden fixture.

## Work Log
- 2026-06-14 [claude]: Status transitioned to complete via cos task-done.
