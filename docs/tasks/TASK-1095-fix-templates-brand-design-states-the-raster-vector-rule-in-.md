---
id: TASK-1095
title: "fix(templates): brand-design states the raster/vector rule in both AGENTS.md and docs/brand.md"
swimlane: templates
kind: bug
epic: workflow-enforcement
labels: [ready]
status: complete
priority: P2
appetite: 2h
created: 2026-11-23
started: 2026-11-23
completed: 2026-11-23
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1095: fix(templates): brand-design states the raster/vector rule in both AGENTS.md and docs/brand.md

**Outcome (one sentence):** A project scaffolded with the brand-design stack states the raster/vector rule once, in docs/brand.md, and AGENTS.md points to it.

## Read First
- docs/playbooks/template-authoring.md
- src/templates/brand-design/fragments/project-rules.md.tmpl
- src/templates/brand-design/scaffold/docs/brand.md

## Repro Steps
rg -n -i 'raster' src/templates/brand-design/fragments/project-rules.md.tmpl src/templates/brand-design/scaffold/docs/brand.md — the same rule appears in both files, so every new brand-design project carries it twice.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the brand-design stack, **When** a project is scaffolded, **Then** the raster/vector rule text appears only in docs/brand.md and the AGENTS.md project rule points to docs/brand.md
- **Given** the template scaffold suite, **When** uv run pytest tests/test_template_scaffold_*.py -q runs, **Then** it passes

## Work Log
- 2026-11-23 [claude]: AGENTS.md project rule 2 now points to docs/brand.md § Production rules instead of restating the raster/vector rule…
- 2026-11-23 [claude]: Status transitioned to complete via cos task-done.
