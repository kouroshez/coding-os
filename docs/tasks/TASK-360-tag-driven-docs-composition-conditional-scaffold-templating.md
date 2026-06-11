---
id: TASK-360
title: "Tag-driven docs composition + conditional scaffold templating"
swimlane: templates
kind: feature
epic: F-docs
labels: [wave-3, onboarding-program, ready]
status: testing
priority: P1
appetite: 2d
created: 2026-06-11
started: 2026-06-11
completed: null
agent_session: ses-claude-20260610-185418-2b3f
depends_on: [TASK-349, TASK-356]
blocked_by: []
references: []
---
# TASK-360: Tag-driven docs composition + conditional scaffold templating

**Outcome (one sentence):** Scaffold docs carry tags (module/stack/option); init copies only docs whose tags match active modules+stacks+options; conditional sections replace raw string-replace so stack-specific guidance renders only when relevant.

## Read First
- src/cli/main.py
- src/templates/_base/scaffold/docs/00-index.md
- src/templates/_base/base.yaml
- src/cli/renderer.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a docs-module-off project, **When** init scaffolds, **Then** governance/PRD doc trees tagged docs-module are absent while untagged kernel docs remain, and the docs index contains no dangling links (docs-lint green).
- **Given** a doc with a stack-conditional section, **When** scaffolded for a project without that stack, **Then** the section is absent; with the stack, present — covered by fixture tests for both branches.
- **Given** a fully-default project, **When** init scaffolds, **Then** output equals pre-change scaffold byte-for-byte (golden), proving backward compatibility.
- **Given** the matrix, **When** `uv run pytest tests/test_template_scaffold.py -q` + `make docs-lint` run, **Then** green.

## Work Log
