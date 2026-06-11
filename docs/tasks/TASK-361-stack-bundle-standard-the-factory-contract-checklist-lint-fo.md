---
id: TASK-361
title: "Stack bundle standard \u2014 the factory contract (checklist + lint for new stacks)"
swimlane: templates
kind: feature
epic: D-catalog
labels: [wave-4, onboarding-program, ready]
status: testing
priority: P1
appetite: 1d
created: 2026-06-11
started: 2026-06-11
completed: null
agent_session: ses-claude-20260610-185418-2b3f
depends_on: [TASK-348, TASK-351, TASK-355]
blocked_by: []
references: []
---
# TASK-361: Stack bundle standard — the factory contract (checklist + lint for new stacks)

**Outcome (one sentence):** A documented + lint-enforced definition of a complete stack bundle (stack.yaml w/ language+structure, stack skill, scrumban-config, >=1 playbook, engineering-rules, verify-matrix row, adapter-parity coverage, golden test) so every future stack is a mechanical 1-task job.

## Read First
- docs/playbooks/template-authoring.md
- src/core/schemas/stack.schema.json
- tests/test_template_scaffold.py
- src/templates/django/stack.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the bundle checklist doc, **When** a reader follows it for a hypothetical stack, **Then** every required artifact and regen step (Rule 10 chain + adapter capability note) is enumerated with its path convention.
- **Given** `cos stack lint <id>` (or make target), **When** run against all 8 existing stacks, **Then** each reports its completeness honestly (django passes; python's known gaps listed) — and a deliberately broken fixture stack fails with named missing artifacts.
- **Given** the factory lint in CI, **When** a new stack omits a bundle artifact, **Then** the test suite fails before merge.
- **Given** the matrix, **When** `uv run pytest tests/test_template_scaffold.py -q` + `make docs-lint` run, **Then** green.

## Work Log
- 2026-06-11 [claude]: Edit stack_lint.py
- 2026-06-11 [claude]: Edit stack_lint.py
- 2026-06-11 [claude]: Edit template-authoring.md
- 2026-06-11 [claude]: Edit stack_lint.py
- 2026-06-11 [claude]: commit b024ec328c — feat(cli): stack bundle factory contract — checklist + cos stack-lint (TASK-361)
- 2026-06-11 [claude]: IMPL DONE (parked, batch 6 #1) — § Stack bundle standard in template-authoring.md (12 rows: hard/soft/manual) + cos stac
