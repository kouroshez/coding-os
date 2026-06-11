---
id: TASK-348
title: "Stack model \u2014 language layer, extends composition, plain-language stacks"
swimlane: templates
kind: feature
epic: C-data-model
labels: [wave-1, onboarding-program, ready]
status: complete
priority: P0
appetite: 2d
created: 2026-06-11
started: 2026-06-10
completed: 2026-06-10
agent_session: ses-claude-20260610-185418-2b3f
depends_on: []
blocked_by: []
references: []
---
# TASK-348: Stack model — language layer, extends composition, plain-language stacks

**Outcome (one sentence):** stack.schema.json gains `language` + `extends` composition; CLI/GUI discovery groups stacks by language (pick language OR framework); go-plain and typescript-plain stacks exist; python stack filled to baseline (skills + minimal docs).

## Read First
- src/core/schemas/stack.schema.json
- src/cli/aggregator.py
- src/cli/main.py
- src/templates/go/stack.yaml
- src/templates/python/stack.yaml
- docs/playbooks/template-authoring.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the updated schema, **When** every existing stack.yaml is validated, **Then** all declare `language` and schema validation passes (extends optional, resolved by the registry loader with cycle detection).
- **Given** `cos init` interactive discovery, **When** the stack prompt renders, **Then** stacks are grouped by language and picking a bare language selects its plain stack (go-plain scaffolds a runnable Go module, typescript-plain a tsconfig project).
- **Given** the python stack, **When** scaffolded, **Then** it ships a baseline skill list and at least one playbook + engineering-rules doc (no longer empty).
- **Given** the matrix commands, **When** `uv run pytest tests/test_cli.py tests/test_template_scaffold.py -q` runs, **Then** new tests for language grouping, extends resolution and plain-stack scaffolds pass with the suite green.

## Work Log
- 2026-06-11 [claude]: Shipped language layer (commit b2261423): stack.schema.json requires `language` + optional `extends`; loader resolves ex
