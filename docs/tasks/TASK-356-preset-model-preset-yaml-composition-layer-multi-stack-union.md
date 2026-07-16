---
id: TASK-356
title: "Preset model \u2014 preset.yaml composition layer + multi-stack union merge"
swimlane: templates
kind: feature
epic: C-data-model
labels: [wave-1, onboarding-program, ready]
status: archive
priority: P0
appetite: 2d
created: 2026-06-11
started: 2026-06-10
completed: 2026-06-11
agent_session: ses-claude-20260610-185418-2b3f
depends_on: [TASK-348, TASK-351]
blocked_by: []
references: []
---
# TASK-356: Preset model — preset.yaml composition layer + multi-stack union merge

**Outcome (one sentence):** preset.yaml schema (stacks[] + modules[] + skills[] + infra options) with `cos init --preset`; multi-stack init produces a union-merged scrumban/rag/domain config (replacing silent last-one-wins) and the merged result is surfaced for preview.

## Read First
- src/cli/main.py
- src/cli/aggregator.py
- src/templates/_base/scaffold/.coding-os/scrumban-config.yaml
- src/templates/django/scaffold/.coding-os/scrumban-config.yaml
- src/core/schemas/stack.schema.json

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a preset.yaml referencing stacks+modules+skills, **When** `cos init --preset <id> --yes` runs, **Then** the project scaffolds with exactly the declared composition and the preset is listed in discovery (CLI + /api/hub data source).
- **Given** init with django+nextjs, **When** configs compose, **Then** scrumban swimlanes are the union of both stacks (stable order, no duplicates), rag/domain configs deep-merge with documented precedence, and a conflict (same key, different values) is reported — never silently dropped.
- **Given** a merge preview request, **When** the wizard or `cos init --dry-config` asks, **Then** the merged swimlane/config summary is returned before any file is written.
- **Given** the matrix, **When** `uv run pytest tests/test_cli.py tests/test_template_scaffold.py -q` runs, **Then** green with preset + merge tests (incl. golden union-merge fixture).

## Work Log
- 2026-06-11 [claude]: committed 78e26f45: docs/engineering/config-composition.md, src/cli/config_composer.py, src/cli/list_stacks.py, src/cli/
- 2026-06-11 [claude]: DONE — preset model: src/templates/_presets/<id>.yaml + preset.schema.json + fail-soft loader (preset_registry.py); cos 
