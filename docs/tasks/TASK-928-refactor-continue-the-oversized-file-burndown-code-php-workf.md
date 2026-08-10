---
id: TASK-928
title: "refactor: continue the oversized-file burndown \u2014 code_php, workflow, _shared, embeddings"
swimlane: core
kind: refactor
epic: null
labels: [tech-debt, file-size, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-08-10
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-928: refactor: continue the oversized-file burndown — code_php, workflow, _shared, embeddings

**Outcome (one sentence):** The next four files in the 800-1000 band drop under the backstop along real cohesion seams, using the five-mechanism verification checklist in the clean-code skill, one commit and one CI pass per file.

## Read First
- src/core/skills/clean-code/SKILL.md
- docs/insights/task-927-splitting-a-module-is-not-a-code-move-it.md
- docs/architecture/raptor-consolidation.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** code_php.py (979) **When** the tree-sitter walk moves to a sibling **Then** the nested emit_* closures no longer force a facade cycle and the graph_os suite passes unchanged.
**Given** each split file **When** its matrix command runs **Then** it passes with no assertion weakened and no new BASELINE entry added.
**Given** a file with no honest seam **When** it is left whole **Then** a recorded exception in ci-gates.md explains why.

## Work Log
