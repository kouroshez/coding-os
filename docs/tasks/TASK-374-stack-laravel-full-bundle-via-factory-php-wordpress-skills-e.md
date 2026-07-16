---
id: TASK-374
title: "Stack: laravel \u2014 full bundle via factory (php/wordpress skills exist)"
swimlane: templates
kind: feature
epic: D-catalog
labels: [backlog, onboarding-program, ready]
status: archive
priority: P2
appetite: 2d
created: 2026-06-11
started: 2026-06-14
completed: 2026-06-14
agent_session: ses-claude-20260614-003127-9cfa
depends_on: [TASK-361]
blocked_by: []
references: []
---
# TASK-374: Stack: laravel — full bundle via factory (php/wordpress skills exist)

**Outcome (one sentence):** Complete laravel stack bundle (language=php, laravel skill reusing core php skill, structure, scrumban, playbook, rules, verify, golden) passing the factory lint.

## Read First
- docs/playbooks/template-authoring.md
- src/core/skills/php/SKILL.md
- docs/engineering/project-anatomy.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the factory contract, **When** `cos init --template laravel --yes --no-index --no-register` runs in a sandbox, **Then** the scaffold lands under the declared structure.root with placeholders resolved and the boundary aggregated.
- **Given** stack.yaml (language=php), **When** schema validation + `make regen-rules` run, **Then** valid, registry rows present, and the laravel skill declares core `php` as secondary (reuse-first, no duplicated PHP content).
- **Given** the matrix, **When** `uv run pytest tests/test_template_scaffold.py tests/test_anatomy_contract.py -q` runs, **Then** green including the golden fixture.

## Work Log
- 2026-06-14 [claude]: Status transitioned to complete via cos task-done.
