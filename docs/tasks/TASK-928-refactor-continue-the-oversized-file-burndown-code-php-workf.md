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
- 2026-08-10 [claude]: commit 5e27b56e48 — docs(insights): record the type-checker re-export trap in a facade split
- 2026-08-10 [claude]: Edit main.py
- 2026-08-10 [claude]: Edit main.py
- 2026-08-10 [claude]: Edit misc.py
- 2026-08-10 [claude]: Edit test_cli.py
- 2026-08-10 [claude]: commit 311aeb227a — fix(cli): register every command before the __main__ guard runs
- 2026-08-10 [claude]: commit 290fa7f6fc — chore(board): record the entrypoint regression fix on TASK-928
- 2026-08-10 [claude]: Edit enumerate_tools.py
- 2026-08-10 [claude]: Edit split_cognition.py
- 2026-08-10 [claude]: Edit _cognition_audit.py
- 2026-08-10 [claude]: Edit pyproject.toml
- 2026-08-10 [claude]: Edit pyproject.toml
- 2026-08-10 [claude]: Edit test_file_size_budget.py
- 2026-08-10 [claude]: commit 5f11a81d39 — refactor(thinking_os): split cognition into supervise, audit, routing and classify
- 2026-08-10 [claude]: Edit enumerate_routes.py
- 2026-08-10 [claude]: Edit split_hub.py
- 2026-08-10 [claude]: Edit split_hub.py
- 2026-08-10 [claude]: Edit split_hub.py
- 2026-08-10 [claude]: Edit pyproject.toml
- 2026-08-10 [claude]: Edit test_hub_init_route.py
- 2026-08-10 [claude]: Edit split_hub.py
- 2026-08-10 [claude]: Edit split_hub.py
- 2026-08-10 [claude]: Edit split_hub.py
- 2026-08-10 [claude]: Edit split_hub.py
- 2026-08-10 [claude]: Edit test_file_size_budget.py
- 2026-08-10 [claude]: commit 7dad131e99 — refactor(web): split hub routes into shared, init, init-routes and scan
- 2026-08-10 [claude]: Edit diff_contracts.py
- 2026-08-10 [claude]: Edit split_contracts.py
- 2026-08-10 [claude]: Edit test_file_size_budget.py
- 2026-08-10 [claude]: commit 2b87fffc58 — refactor(graph_os): split the contracts extractor into one module per ecosystem
- 2026-08-10 [claude]: Edit split_doctor.py
- 2026-08-10 [claude]: Edit split_doctor.py
- 2026-08-10 [claude]: Edit split_doctor.py
- 2026-08-10 [claude]: Edit split_doctor.py
- 2026-08-10 [claude]: Edit split_doctor.py
- 2026-08-10 [claude]: Edit test_file_size_budget.py
- 2026-08-10 [claude]: commit b77220bf61 — refactor(cli): split doctor_extras into runtime, adapter and project checks
- 2026-08-10 [claude]: Edit ci-gates.md
- 2026-08-10 [claude]: commit fbb77e5a4e — docs(ci-gates): record the four burndown splits and the two traps they surfaced
- 2026-08-10 [claude]: cognition.py 1237 to 81: split into _cognition_supervise/_audit/_routing/_classify. Live 87-tool MCP registry (names,…
- 2026-08-10 [claude]: hub.py 1217 to 326: split into _hub_shared/_hub_init/_hub_init_routes/_hub_scan. Router moved to the leaf after a…
- 2026-08-10 [claude]: contracts.py 1196 to 310 (commit 2b87fffc) and doctor_extras.py 1121 to 85 (commit b77220bf). Contracts differential…
- 2026-08-10 [claude]: Pre-existing failure found, NOT caused by this slice: tests/test_doctor.py::test_doctor_detects_stale_codex_hook_map…
- 2026-08-10 [claude]: commit 8c25e856ad — chore(board): record the four-file burndown slice on TASK-928
- 2026-08-10 [claude]: Edit _doctor_adapters.py
- 2026-08-10 [claude]: Edit scan_returns.py
- 2026-08-10 [claude]: Edit ci-gates.md
- 2026-08-10 [claude]: Edit ci-gates.md
- 2026-08-10 [claude]: Edit mypy_ratchet.py
- 2026-08-10 [claude]: Edit mypy_ratchet.py
- 2026-08-10 [claude]: commit d76583fb3f — fix(cli): restore the dropped return in _normalized_hook_map
- 2026-08-10 [claude]: commit ac6ec75af3 — chore(board): record the doctor regression and the fatal-code gate on TASK-928
- 2026-08-10 [claude]: Edit check_split_parity.py
- 2026-08-10 [claude]: Edit audit_splits.sh
- 2026-08-10 [claude]: Edit check_split_parity.py
- 2026-08-10 [claude]: Edit check_split_parity.py
- 2026-08-10 [claude]: Edit check_split_parity.py
- 2026-08-11 [claude]: Edit check_split_parity.py
- 2026-08-11 [claude]: Edit check_split_parity.py
- 2026-08-11 [claude]: Edit show_diff.py
- 2026-08-11 [claude]: Edit ci-gates.md
- 2026-08-11 [claude]: Edit SKILL.md
- 2026-08-11 [claude]: commit 1b1f50808b — feat(scripts): add a split-parity guard that proves a module move edited nothing
- 2026-08-11 [claude]: Edit _board_shared.py
- 2026-08-11 [claude]: Edit _board_presence.py
- 2026-08-11 [claude]: Edit _board_autospawn.py
- 2026-08-11 [claude]: Edit _board_git.py
- 2026-08-11 [claude]: Edit _board_tasks.py
- 2026-08-11 [claude]: Edit _board_views.py
- 2026-08-11 [claude]: Edit board.py
- 2026-08-11 [claude]: Edit board.py
- 2026-08-11 [claude]: Edit board.py
- 2026-08-11 [claude]: Edit board.py
- 2026-08-11 [claude]: Edit board.py
- 2026-08-11 [claude]: Edit board.py
- 2026-08-11 [claude]: Edit test_hub_settings_auto_spawn.py
- 2026-08-11 [claude]: Edit test_file_size_budget.py
- 2026-08-11 [claude]: Edit _board_presence.py
- 2026-08-11 [claude]: Edit ci-gates.md
- 2026-08-11 [claude]: commit 11721b0e89 — refactor(web): split board routes into shared, presence, autospawn, git and view modules
- 2026-08-11 [claude]: Edit _learning_generalize.py
- 2026-08-11 [claude]: Edit _learning_extract.py
- 2026-08-11 [claude]: Edit _learning_suggest.py
- 2026-08-11 [claude]: Edit _learning_validate.py
- 2026-08-11 [claude]: Edit learning.py
- 2026-08-11 [claude]: Edit ci-gates.md
- 2026-08-11 [claude]: commit 789c734b41 — refactor(thinking_os): split learning into extract, suggest, validate and generalize modules
- 2026-08-11 [claude]: Edit ci-gates.md
- 2026-08-11 [claude]: commit 934695334d — refactor(graph_os): split the sqlite backend into a connection base and three mixins
- 2026-08-11 [claude]: Edit _mcp_stranded.py
- 2026-08-11 [claude]: Edit ci-gates.md
- 2026-08-11 [claude]: commit 54d08b0ada — refactor(board_os): split reclaim into stranded, pick, report and work-log modules
- 2026-08-11 [claude]: commit c09660f7bf — chore(board): record the batch-six splits on TASK-928
- 2026-08-11 [claude]: Edit _ts_uids.py
- 2026-08-11 [claude]: Edit _ts_nodes.py
- 2026-08-11 [claude]: Edit pyproject.toml
- 2026-08-11 [claude]: commit ff6824e758 — refactor(graph_os): split code_ts into a uid leaf, node primitives, symbol walk and regex scanners
- 2026-08-11 [claude]: Edit _ts_symbols.py
- 2026-08-11 [claude]: Edit _ts_decls.py
- 2026-08-11 [claude]: commit b23a6d7677 — refactor(graph_os): decompose the ts symbol walk into a declaration pass and a call pass
- 2026-08-11 [claude]: commit b4ff3fbdce — refactor(graph_os): split md_links into a shared base leaf, uids, resolve and section modules
- 2026-08-11 [claude]: commit a1e64889b8 — refactor(thinking_os): split doc_indexer into chunking, sources and store modules
- 2026-08-11 [claude]: commit 5452fba25c — refactor(thinking_os): split memory tools into ranking, semantic and search modules
- 2026-08-11 [claude]: Batch seven — code_ts 930 + _code_ts_regex 782 → 7 modules (max 413); md_links 890 → 6 modules (max 298, shared…
- 2026-08-11 [claude]: Verification: check_split_parity OK on all 5 pre-split files; behavioural differentials byte-identical (120 TS files…
