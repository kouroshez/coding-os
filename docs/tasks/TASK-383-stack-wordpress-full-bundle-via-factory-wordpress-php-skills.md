---
id: TASK-383
title: "Stack: wordpress \u2014 full bundle via factory (wordpress+php skills exist)"
swimlane: templates
kind: feature
epic: D-catalog
labels: [backlog, onboarding-program, ready]
status: icebox
priority: P3
appetite: 1d
created: 2026-06-11
started: null
completed: null
agent_session: null
depends_on: [TASK-361]
blocked_by: []
references: []
---

# TASK-383: Stack: wordpress — full bundle via factory (wordpress+php skills exist)

**Outcome (one sentence):** Complete wordpress stack bundle (language=php, reuses existing wordpress + php core skills) passing the factory lint.

## Read First
- docs/playbooks/template-authoring.md
- src/core/skills/wordpress/SKILL.md
- docs/engineering/project-anatomy.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the factory contract, **When** `cos init --template wordpress --yes --no-index --no-register` runs in a sandbox, **Then** scaffold lands under the declared structure.root (theme/plugin convention) with placeholders resolved.
- **Given** stack.yaml (language=php), **When** schema validation + `make regen-rules` run, **Then** valid; primary_skill is the EXISTING core `wordpress` skill with `php` secondary — zero new skill content authored.
- **Given** the matrix, **When** `uv run pytest tests/test_template_scaffold.py tests/test_anatomy_contract.py -q` runs, **Then** green including the golden fixture.

## Work Log
