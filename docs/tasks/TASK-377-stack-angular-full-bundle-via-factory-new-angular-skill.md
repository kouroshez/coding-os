---
id: TASK-377
title: "Stack: angular \u2014 full bundle via factory (new angular skill)"
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
- 2026-06-14 [claude]: Edit app.component.ts
- 2026-06-14 [claude]: Edit aspnet-core-rules.md
- 2026-06-14 [claude]: Edit global-error-handler.ts
- 2026-06-14 [claude]: Edit astro-app.md
- 2026-06-14 [claude]: Edit health.service.ts
- 2026-06-14 [claude]: Edit backend.md
- 2026-06-14 [claude]: Edit astro-rules.md
- 2026-06-14 [claude]: Edit health.component.ts
- 2026-06-14 [claude]: Edit package.json
- 2026-06-14 [claude]: Edit SKILL.md
- 2026-06-14 [claude]: Edit tsconfig.json
- 2026-06-14 [claude]: Edit SKILL.md
- 2026-06-14 [claude]: Edit angular.json
- 2026-06-14 [claude]: Edit stack.yaml
- 2026-06-14 [claude]: Edit index.html
- 2026-06-14 [claude]: Edit scaffold-boundary.yaml
- 2026-06-14 [claude]: Edit styles.css
- 2026-06-14 [claude]: Edit Backend.csproj
- 2026-06-14 [claude]: Edit Program.cs
- 2026-06-14 [claude]: Status transitioned to complete via cos task-done.
