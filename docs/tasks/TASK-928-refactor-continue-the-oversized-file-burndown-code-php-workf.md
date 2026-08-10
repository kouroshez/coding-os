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
- 2026-08-10 [claude]: commit 926297dc03 — refactor(board_os): split workflow into types, wip, deps, frontmatter, and gates
- 2026-08-10 [claude]: HANDOFF — 2 of 4 files done (code_php 979→300, workflow 964→422), both committed with CI green. Remaining:…
- 2026-08-10 [claude]: commit 69fd898067 — chore(board): record the workflow split and the handoff note on TASK-928
- 2026-08-10 [claude]: Edit capture_shared_baseline.py
- 2026-08-10 [claude]: Edit capture_shared_baseline.py
- 2026-08-10 [claude]: Edit capture_shared_baseline.py
- 2026-08-10 [claude]: Edit _envelope_size.py
- 2026-08-10 [claude]: Edit _envelope_subgraph.py
- 2026-08-10 [claude]: Edit _envelope_trim.py
- 2026-08-10 [claude]: Edit _envelope_errors.py
- 2026-08-10 [claude]: Edit _envelope_gating.py
- 2026-08-10 [claude]: Edit _envelope_gating.py
- 2026-08-10 [claude]: Edit _shared.py
- 2026-08-10 [claude]: Edit _shared.py
- 2026-08-10 [claude]: Edit _envelope_trim.py
- 2026-08-10 [claude]: Edit _envelope_subgraph.py
- 2026-08-10 [claude]: Edit test_file_size_budget.py
- 2026-08-10 [claude]: Edit pyproject.toml
- 2026-08-10 [claude]: Edit annotate_envelope.py
- 2026-08-10 [claude]: Edit pyproject.toml
- 2026-08-10 [claude]: Edit _shared.py
- 2026-08-10 [claude]: Edit check_identities.py
- 2026-08-10 [claude]: Edit commit_shared.txt
- 2026-08-10 [claude]: commit d11b6ceae5 — refactor(thinking_os): split the MCP envelope into size, trim, subgraph, errors, and gating
- 2026-08-10 [claude]: _shared.py 947 → 398: split into _envelope_size (measurement leaf), _envelope_trim (the ladder), _envelope_subgraph…
- 2026-08-10 [claude]: commit d11b6cea — verified by differential against the pre-split module (trim ladder, validators, safe_tool exception…
- 2026-08-10 [claude]: Edit ci-gates.md
- 2026-08-10 [claude]: Edit commit_docs.txt
- 2026-08-10 [claude]: commit bf34bad901 — docs(ci-gates): record why embeddings.py stays whole and how the envelope split cleared mypy
- 2026-08-10 [claude]: embeddings.py (943) left whole — recorded exception in ci-gates.md (commit bf34bad9). It has cohesion seams but none…
- 2026-08-10 [claude]: commit a0420a92e6 — chore(board): record the envelope split and the embeddings blocker on TASK-928
- 2026-08-10 [claude]: Edit extract_snapshot.py
- 2026-08-10 [claude]: Edit extract_snapshot.py
- 2026-08-10 [claude]: Edit extract_snapshot.py
- 2026-08-10 [claude]: Edit extract_snapshot.py
- 2026-08-10 [claude]: Edit extract_snapshot.py
- 2026-08-10 [claude]: Edit split_py.py
- 2026-08-10 [claude]: Edit split_py_emit.py
- 2026-08-10 [claude]: Edit split_py_facade.py
- 2026-08-10 [claude]: Edit pyproject.toml
- 2026-08-10 [claude]: Edit extract_snapshot.py
- 2026-08-10 [claude]: Edit extract_snapshot.py
- 2026-08-10 [claude]: Edit extract_snapshot.py
- 2026-08-10 [claude]: Edit test_file_size_budget.py
- 2026-08-10 [claude]: Edit test_code_python.py
- 2026-08-10 [claude]: commit 92858a41c8 — refactor(graph_os): split code_python into uid, decl, tree-sitter, visitor and emit modules
- 2026-08-10 [claude]: Edit harvest_go.py
- 2026-08-10 [claude]: Edit go_snapshot.py
- 2026-08-10 [claude]: Edit split_go.py
- 2026-08-10 [claude]: Edit _go_uids.py
- 2026-08-10 [claude]: commit abcf45255c — refactor(graph_os): split code_go into uid, symbol, type, package, call and regex modules
- 2026-08-10 [claude]: Edit cli_surface.py
- 2026-08-10 [claude]: Edit plan_cli.py
- 2026-08-10 [claude]: Edit split_cli.py
- 2026-08-10 [claude]: commit 90f4b25060 — refactor(cli): split main into path leaf, init, adopt, install and runtime command modules
- 2026-08-10 [claude]: Burned down three more god-files (92858a41, abcf4525, 90f4b250): code_python 1454->242, code_go 1422->322, cli/main…
- 2026-08-10 [claude]: Edit graph_snapshot.py
- 2026-08-10 [claude]: Edit graph_snapshot.py
- 2026-08-10 [claude]: Edit graph_snapshot.py
- 2026-08-10 [claude]: Edit bounds.py
- 2026-08-10 [claude]: Edit split_graph_kernel.py
- 2026-08-10 [claude]: Edit pyproject.toml
- 2026-08-10 [claude]: Edit diffcalls.py
- 2026-08-10 [claude]: Edit mcp_registry.py
- 2026-08-10 [claude]: Edit mypy_diff.py
- 2026-08-10 [claude]: Edit alias_reexports.py
- 2026-08-10 [claude]: Edit fix_alias.py
- 2026-08-10 [claude]: Edit test_file_size_budget.py
- 2026-08-10 [claude]: commit 4b83aa39cd — refactor(graph_os): split the graph kernel into envelope, walk and lookup leaves
- 2026-08-10 [claude]: Edit split_graph_read.py
- 2026-08-10 [claude]: Edit prune_imports.py
- 2026-08-10 [claude]: Edit split_graph_read.py
- 2026-08-10 [claude]: Edit _graph_read.py
- 2026-08-10 [claude]: Edit pyproject.toml
- 2026-08-10 [claude]: Edit graph.py
- 2026-08-10 [claude]: Edit test_file_size_budget.py
- 2026-08-10 [claude]: commit 69a41cca4e — refactor(graph_os): split the read tools into read, paths, references and similar
- 2026-08-10 [claude]: Edit split_graph_insights.py
- 2026-08-10 [claude]: Edit _graph_envelope.py
- 2026-08-10 [claude]: Edit graph.py
- 2026-08-10 [claude]: Edit graph.py
- 2026-08-10 [claude]: Edit graph.py
- 2026-08-10 [claude]: Edit graph.py
- 2026-08-10 [claude]: Edit graph.py
- 2026-08-10 [claude]: Edit pyproject.toml
- 2026-08-10 [claude]: Edit test_file_size_budget.py
- 2026-08-10 [claude]: commit 5a76647fff — refactor(graph_os): split the insight tools into structure, centrality, ranking and hygiene
- 2026-08-10 [claude]: Edit split_graph_cli.py
- 2026-08-10 [claude]: Edit graph_commands.py
- 2026-08-10 [claude]: Edit pyproject.toml
- 2026-08-10 [claude]: Edit graph_commands.py
- 2026-08-10 [claude]: Edit test_file_size_budget.py
- 2026-08-10 [claude]: commit cb86e0a5f8 — refactor(cli): split graph commands into shared, query, reindex, ingest and group modules
- 2026-08-10 [claude]: Edit split_board_cli.py
- 2026-08-10 [claude]: Edit pyproject.toml
- 2026-08-10 [claude]: Edit test_file_size_budget.py
- 2026-08-10 [claude]: Edit board_commands.py
- 2026-08-10 [claude]: Edit graph_commands.py
- 2026-08-10 [claude]: commit 9a8dccf666 — refactor(cli): split board commands into shared, lifecycle, views, outcome and validate
- 2026-08-10 [claude]: graph_os tool layer + CLI slice: graph.py 1271→369, _graph_read 1256→375, _graph_insights 1248→315, graph_commands…
- 2026-08-10 [claude]: commit c8d13fe906 — chore(board): record the graph_os tool-layer and CLI splits on TASK-928
