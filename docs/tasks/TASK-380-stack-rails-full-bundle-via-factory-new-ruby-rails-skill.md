---
id: TASK-380
title: "Stack: rails \u2014 full bundle via factory (new ruby/rails skill)"
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
- 2026-06-14 [claude]: Edit SKILL.md
- 2026-06-14 [claude]: Edit main.rs
- 2026-06-14 [claude]: Edit app.rs
- 2026-06-14 [claude]: Edit error.rs
- 2026-06-14 [claude]: Edit mod.rs
- 2026-06-14 [claude]: Edit health.rs
- 2026-06-14 [claude]: Edit rust-axum-service.md
- 2026-06-14 [claude]: Edit SKILL.md
- 2026-06-14 [claude]: Edit rust-axum-rules.md
- 2026-06-14 [claude]: Edit stack.yaml
- 2026-06-14 [claude]: Edit Cargo.toml
- 2026-06-14 [claude]: Edit main.rs
- 2026-06-14 [claude]: Edit stack.yaml
- 2026-06-14 [claude]: Edit scaffold-boundary.yaml
- 2026-06-14 [claude]: Edit SKILL.md
- 2026-06-14 [claude]: Edit SKILL.md
- 2026-06-14 [claude]: commit 5ca7b59b3d — feat(skills): add horizontal skill bundles 1+2 (8 cross-cutting skills)
- 2026-06-14 [claude]: Edit stack.yaml
- 2026-06-14 [claude]: Edit scaffold-boundary.yaml
- 2026-06-14 [claude]: Edit scrumban-config.yaml
- 2026-06-14 [claude]: Edit composer.json
- 2026-06-14 [claude]: Edit index.php
- 2026-06-14 [claude]: Edit api.php
- 2026-06-14 [claude]: Edit HealthController.php
- 2026-06-14 [claude]: Edit Handler.php
- 2026-06-14 [claude]: Edit laravel-service.md
- 2026-06-14 [claude]: Edit laravel-rules.md
- 2026-06-14 [claude]: Edit SKILL.md
- 2026-06-14 [claude]: Edit stack.yaml
- 2026-06-14 [claude]: Edit scaffold-boundary.yaml
- 2026-06-14 [claude]: Edit scrumban-config.yaml
- 2026-06-14 [claude]: Edit functions.php
- 2026-06-14 [claude]: Edit style.css
- 2026-06-14 [claude]: Edit plugin.php
- 2026-06-14 [claude]: Edit wordpress-service.md
- 2026-06-14 [claude]: Edit wordpress-rules.md
- 2026-06-14 [claude]: commit f242591a39 — feat(templates): add laravel + wordpress php stacks via factory
- 2026-06-14 [claude]: Edit mean.yaml
- 2026-06-14 [claude]: Edit tall.yaml
- 2026-06-14 [claude]: Edit jamstack.yaml
- 2026-06-14 [claude]: Edit flutter-baas.yaml
- 2026-06-14 [claude]: Edit spring-react.yaml
- 2026-06-14 [claude]: Edit rails-react.yaml
- 2026-06-14 [claude]: Edit dotnet-react.yaml
- 2026-06-14 [claude]: Edit nest-angular.yaml
- 2026-06-14 [claude]: Edit rust-svelte.yaml
- 2026-06-14 [claude]: Edit wordpress-cms.yaml
- 2026-06-14 [claude]: commit 2d0426dce3 — feat(templates): add 10 world presets v2 from new stacks (TASK-386)
- 2026-06-14 [claude]: Status transitioned to complete via cos task-done.
