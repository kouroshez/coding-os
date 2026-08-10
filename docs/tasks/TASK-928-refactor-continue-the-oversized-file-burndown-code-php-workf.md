---
id: TASK-928
title: "refactor: continue the oversized-file burndown \u2014 code_php, workflow, _shared, embeddings"
swimlane: core
kind: refactor
epic: null
labels: [tech-debt, file-size, ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-08-10
started: 2026-08-10
completed: null
agent_session: ses-claude-20260807-224955-abc1
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
- 2026-08-10 [claude]: Edit _php_uids.py
- 2026-08-10 [claude]: Edit _php_calls.py
- 2026-08-10 [claude]: Edit _php_symbols.py
- 2026-08-10 [claude]: Edit code_php.py
- 2026-08-10 [claude]: Edit pyproject.toml
- 2026-08-10 [claude]: Edit verify_php_split.py
- 2026-08-10 [claude]: Edit verify_php_split.py
- 2026-08-10 [claude]: Edit verify_php_split.py
- 2026-08-10 [claude]: Edit diff_php_baseline.py
- 2026-08-10 [claude]: Edit verify_php_split.py
- 2026-08-10 [claude]: Edit test_file_size_budget.py
- 2026-08-10 [claude]: Edit mypy_ratchet.py
- 2026-08-10 [claude]: Edit ci-gates.md
- 2026-08-10 [claude]: code_php.py 979 → 300: split into _php_uids (leaf: uid grammar + node primitives), _php_symbols (declaration walker,…
- 2026-08-10 [claude]: commit 1bf573adc5 — refactor(graph_os): split code_php into a uid leaf, symbol walker, and call walker
- 2026-08-10 [claude]: Edit _workflow_types.py
- 2026-08-10 [claude]: Edit _workflow_deps.py
- 2026-08-10 [claude]: Edit _workflow_frontmatter.py
- 2026-08-10 [claude]: Edit _workflow_wip.py
- 2026-08-10 [claude]: Edit _workflow_gates.py
- 2026-08-10 [claude]: Edit _workflow_gates.py
- 2026-08-10 [claude]: Edit _workflow_gates.py
- 2026-08-10 [claude]: Edit workflow.py
- 2026-08-10 [claude]: Edit diff_workflow_baseline.py
- 2026-08-10 [claude]: Edit pyproject.toml
- 2026-08-10 [claude]: Edit verify_workflow_split.py
- 2026-08-10 [claude]: Edit pyproject.toml
- 2026-08-10 [claude]: Edit mypy_ratchet.py
- 2026-08-10 [claude]: Edit ci-gates.md
- 2026-08-10 [claude]: workflow.py 964 → 422: split into _workflow_types (leaf: edges, WIP columns, result types), _workflow_wip (65),…
