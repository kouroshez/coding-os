---
id: TASK-381
title: "Stack: rust-axum \u2014 full bundle via factory (new rust skill + rust-plain)"
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
# TASK-381: Stack: rust-axum — full bundle via factory (new rust skill + rust-plain)

**Outcome (one sentence):** Complete rust-axum stack bundle including a new rust skill and rust-plain language stack passing the factory lint.

## Read First
- docs/playbooks/template-authoring.md
- src/templates/go/stack.yaml + src/templates/go-plain/stack.yaml (language+framework pair pattern)
- docs/engineering/project-anatomy.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the language layer, **When** `rust-plain` + `rust-axum` stacks load, **Then** bare "rust" resolves to rust-plain (cargo skeleton) and rust-axum declares language=rust.
- **Given** the factory contract, **When** `cos init --template rust-axum --yes --no-index --no-register` runs, **Then** scaffold lands under structure.root `src/backend` with a buildable cargo skeleton and resolved placeholders.
- **Given** the new rust SKILL.md, **When** the skill registry loads, **Then** schema-valid frontmatter with no warnings.
- **Given** the matrix, **When** `uv run pytest tests/test_template_scaffold.py tests/test_anatomy_contract.py -q` runs, **Then** green including golden fixtures.

## Work Log
- 2026-06-14 [claude]: Status transitioned to complete via cos task-done.
