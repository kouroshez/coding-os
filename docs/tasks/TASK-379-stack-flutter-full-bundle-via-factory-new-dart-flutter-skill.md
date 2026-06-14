---
id: TASK-379
title: "Stack: flutter \u2014 full bundle via factory (new dart/flutter skill)"
swimlane: templates
kind: feature
epic: D-catalog
labels: [backlog, onboarding-program, ready]
status: complete
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
# TASK-379: Stack: flutter — full bundle via factory (new dart/flutter skill)

**Outcome (one sentence):** Complete flutter stack bundle including a new dart/flutter skill (language=dart, mobile category, reuses mobile-fundamentals) passing the factory lint.

## Read First
- docs/playbooks/template-authoring.md
- src/templates/react-native/stack.yaml (mobile-category shape)
- docs/engineering/project-anatomy.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the factory contract, **When** `cos init --template flutter --yes --no-index --no-register` runs in a sandbox, **Then** scaffold lands under structure.root `src/mobile` with placeholders resolved and the boundary aggregated.
- **Given** stack.yaml (language=dart, category=mobile), **When** schema validation + `make regen-rules` run, **Then** valid; the flutter skill declares `mobile-fundamentals` + `a11y` as secondaries (reuse-first).
- **Given** the new dart/flutter SKILL.md, **When** the skill registry loads, **Then** schema-valid frontmatter with no warnings.
- **Given** the matrix, **When** `uv run pytest tests/test_template_scaffold.py tests/test_anatomy_contract.py -q` runs, **Then** green including the golden fixture.

## Work Log
- 2026-06-14 [claude]: Status transitioned to complete via cos task-done.
