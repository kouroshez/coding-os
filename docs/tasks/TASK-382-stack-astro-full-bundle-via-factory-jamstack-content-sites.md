---
id: TASK-382
title: "Stack: astro \u2014 full bundle via factory (JAMstack/content sites)"
swimlane: templates
kind: feature
epic: D-catalog
labels: [backlog, onboarding-program, ready]
status: complete
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
# TASK-382: Stack: astro — full bundle via factory (JAMstack/content sites)

**Outcome (one sentence):** Complete astro stack bundle (language=typescript, content/SEO orientation, reuses frontend-design + content playbooks) passing the factory lint.

## Read First
- docs/playbooks/template-authoring.md
- src/templates/nextjs/scaffold/docs/playbooks/content-seo.md
- docs/engineering/project-anatomy.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the factory contract, **When** `cos init --template astro --yes --no-index --no-register` runs in a sandbox, **Then** scaffold lands under structure.root `src/frontend` with placeholders resolved and the boundary aggregated.
- **Given** stack.yaml (language=typescript, category=frontend), **When** schema validation + `make regen-rules` run, **Then** valid; content/SEO dimension routes to the shared content-seo playbook (reuse, no duplicate doc).
- **Given** the matrix, **When** `uv run pytest tests/test_template_scaffold.py tests/test_anatomy_contract.py -q` runs, **Then** green including the golden fixture.

## Work Log
- 2026-06-14 [claude]: Status transitioned to complete via cos task-done.
