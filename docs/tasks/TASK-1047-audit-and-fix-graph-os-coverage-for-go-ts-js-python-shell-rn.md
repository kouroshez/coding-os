---
id: TASK-1047
title: "Audit and fix graph_os coverage for Go, TS, JS, Python, Shell + RN, Fiber, Astro, FastAPI"
swimlane: "graph_os"
kind: bug
epic: null
labels: [ready, docs-update]
status: complete
priority: P1
appetite: 3d
created: 2026-10-05
started: 2026-10-04
completed: 2026-10-07
agent_session: ses-claude-20261004-231430-d18a
depends_on: []
blocked_by: []
references: []
---
# TASK-1047: Audit and fix graph_os coverage for Go, TS, JS, Python, Shell + RN, Fiber, Astro, FastAPI

**Outcome (one sentence):** Every confirmed defect in how graph_os indexes Go, TypeScript, JavaScript, Python and Shell — and the React Native, Go Fiber, Astro and FastAPI framework surfaces — is fixed with a regression test, one commit per fix; the audit doc answers the seven completeness questions with measured evidence.

## Read First
- docs/engineering/graph-os-polyglot-audit-2026-10-04.md
- docs/playbooks/polyglot-extractor-roadmap.md
- docs/engineering/graph_os-queries.md
- docs/engineering/graph-hallucination-cures.md

## Repro Steps
Probe each extractor with adversarial fixtures per language/framework (cross-file same-package Go calls, TS .js-suffixed ESM imports, CommonJS require, Python module-alias calls, Fiber group prefixes, FastAPI include_router prefixes, .astro files) and compare emitted nodes/edges to ground truth.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the audit doc, **When** a reviewer reads it, **Then** each of the seven questions has a yes/no/partial answer backed by a reproduced probe.
- **Given** a confirmed defect in the checklist, **When** it is fixed, **Then** a regression test fails before the fix and passes after, and the fix lands in its own commit.
- **Given** the graph_os matrix row, **When** it runs at close, **Then** `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` is green and `make lint` passes on the touched files.

## Work Log
- 2026-10-05 [claude]: Plan: 7 read-only auditors (go-fiber, ts-js-rn, astro, python-fastapi, shell, cross-cutting completeness, web…
- 2026-10-05 [claude]: commit f9c306e0eb — docs(graph_os): open the polyglot audit register for Go, TS, JS, Python and Shell
- 2026-10-05 [claude]: Edit test_reindex_dispatch.py
- 2026-10-05 [claude]: Edit test_reindex_dispatch.py
- 2026-10-05 [claude]: Edit resolve.go
- 2026-10-05 [claude]: Edit _sqlite_write.py
- 2026-10-05 [claude]: Edit _sqlite_write.py
- 2026-10-05 [claude]: Edit main.go
- 2026-10-05 [claude]: Edit _reindex_layers.py
- 2026-10-05 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-05 [claude]: commit 977f2b9e4c — fix(graph_os): keep inbound cross-file edges when a file is reindexed
- 2026-10-05 [claude]: F-01 fixed (977f2b9e): per-file reindex pruned nodes before re-extract; ON DELETE CASCADE erased every inbound…
- 2026-10-05 [claude]: Edit main.go
- 2026-10-05 [claude]: Edit main.go
- 2026-10-05 [claude]: Edit test_sqlite_write_rollback.py
- 2026-10-05 [claude]: Edit _sqlite_write.py
- 2026-10-05 [claude]: Edit _sqlite_write.py
- 2026-10-05 [claude]: Edit _sqlite_write.py
- 2026-10-05 [claude]: Edit test_sqlite_write_rollback.py
- 2026-10-05 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-05 [claude]: commit 9f60c959db — fix(graph_os): stop parallel reindex workers failing files on a write race
- 2026-10-05 [claude]: Edit types.py
- 2026-10-05 [claude]: Edit types.py
- 2026-10-05 [claude]: Edit types.py
- 2026-10-05 [claude]: Edit _reindex_layers.py
- 2026-10-05 [claude]: Edit _reindex_layers.py
- 2026-10-05 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-05 [claude]: commit 61d4c63d36 — fix(graph_os): prune every ID an extractor stamps so renamed TS symbols do not linger
- 2026-10-05 [claude]: Edit main.go
- 2026-10-05 [claude]: Edit main.go
- 2026-10-05 [claude]: Edit resolve_ts.py
- 2026-10-05 [claude]: Edit toolchain.py
- 2026-10-05 [claude]: Edit toolchain.py
- 2026-10-05 [claude]: Edit toolchain.py
- 2026-10-05 [claude]: Edit test_resolve_ts.py
- 2026-10-05 [claude]: Edit test_toolchain.py
- 2026-10-05 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-05 [claude]: commit e659222683 — fix(graph_os): keep URL strings intact when stripping JSONC comments
- 2026-10-05 [claude]: Edit resolve_ts.py
- 2026-10-05 [claude]: Edit resolve_ts.py
- 2026-10-05 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-05 [claude]: Edit _sqlite_links_ts.py
- 2026-10-05 [claude]: Edit _reindex_layers.py
- 2026-10-05 [claude]: Edit _reindex_layers.py
- 2026-10-05 [claude]: Edit _reindex_layers.py
- 2026-10-05 [claude]: Edit test_ts_cross_file_links.py
- 2026-10-05 [claude]: commit 7be6958d68 — fix(graph_os): resolve TS/JS imports like TypeScript and link them across files
- 2026-10-05 [claude]: Edit resolve_go.py
- 2026-10-05 [claude]: Edit _sqlite_links_go.py
- 2026-10-05 [claude]: Edit test_go_cross_file_links.py
- 2026-10-05 [claude]: commit fecdf07364 — fix(graph_os): link Go calls, types and imports across files and packages
- 2026-10-05 [claude]: Progress: committed F-01 inbound-edge cascade, F-03 write race, F-04 TS zombie prune, F-05 JSONC $schema, CC-12 stub…
- 2026-10-05 [claude]: Edit test_extension_coverage.py
- 2026-10-05 [claude]: Edit auto-reindex-docs.sh
- 2026-10-05 [claude]: Edit auto-reindex-docs.sh
- 2026-10-05 [claude]: Edit auto-reindex-docs.sh
- 2026-10-05 [claude]: Edit auto-reindex-docs.sh
- 2026-10-05 [claude]: Edit _shell_paths.py
- 2026-10-05 [claude]: Edit _shell_commands.py
- 2026-10-05 [claude]: Edit _sqlite_links_sh.py
- 2026-10-05 [claude]: Edit test_shell_dependencies.py
- 2026-10-05 [claude]: commit e945c7ee7e — fix(graph_os): follow shell sources, helper runs and library calls across files
- 2026-10-05 [claude]: Edit test_python_cross_file_links.py
- 2026-10-05 [claude]: Edit _tools_graph_query.py
- 2026-10-05 [claude]: Edit _fingerprint.py
- 2026-10-05 [claude]: Edit _graph_clones.py
- 2026-10-05 [claude]: Edit test_duplicates.py
- 2026-10-05 [claude]: CC-05 (Q2 duplicates): per-declaration body fingerprints in all 5 languages (content_hash exact / ast_hash renamed,…
- 2026-10-05 [claude]: commit 41194fbdf1 — feat(graph_os): find copy-pasted code from per-symbol body fingerprints
- 2026-10-05 [claude]: Edit test_paths.py
- 2026-10-05 [claude]: Edit test_test_paths.py
- 2026-10-05 [claude]: commit fd32086791 — fix(graph_os): treat Go, TS and Jest test files as tests in every tool
- 2026-10-05 [claude]: Edit _go_routes.py
- 2026-10-05 [claude]: Edit _go_routes.py
- 2026-10-05 [claude]: Edit test_go_fiber_routes.py
- 2026-10-05 [claude]: commit dc50c4320a — fix(graph_os): read Fiber routes from typed routers with the last argument as handler
- 2026-10-05 [claude]: commit 2b2ff63215 — fix(graph_os): keep Go type parameters out of type and call edges
- 2026-10-05 [claude]: Edit _undefined_names.py
- 2026-10-05 [claude]: Edit _graph_undefined.py
- 2026-10-05 [claude]: Edit test_undefined_names.py
- 2026-10-05 [claude]: commit 4c60c9d511 — feat(graph_os): report names the code uses but never defines or imports
- 2026-10-05 [claude]: Edit test_library_fan_in.py
- 2026-10-05 [claude]: Edit _contracts_fastapi.py
- 2026-10-05 [claude]: Edit _sqlite_links_routes.py
- 2026-10-05 [claude]: Edit test_fastapi_routes.py
- 2026-10-05 [claude]: commit fbfc535931 — fix(graph_os): compose FastAPI route paths across the files that build them
- 2026-10-05 [claude]: Edit _ts_exports.py
- 2026-10-05 [claude]: Edit _ts_exports.py
- 2026-10-05 [claude]: Edit test_ts_imports_exports.py
- 2026-10-05 [claude]: commit b172f4641c — fix(graph_os): bind TS imports by exported name and give exported values a node
- 2026-10-05 [claude]: Edit _contracts_file_routes.py
- 2026-10-05 [claude]: Edit test_file_routes.py
- 2026-10-05 [claude]: commit f82601303b — feat(graph_os): read Expo Router, Astro and TanStack file routes by the package's router
- 2026-10-05 [claude]: Edit test_python_dependencies.py
- 2026-10-05 [claude]: commit 220afc83c5 — fix(graph_os): keep TYPE_CHECKING imports type-only and the first of a fallback import
- 2026-10-05 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-05 [claude]: Edit SKILL.md
- 2026-10-05 [claude]: Edit SKILL.md
- 2026-10-05 [claude]: Edit SKILL.md
- 2026-10-05 [claude]: Edit SKILL.md
- 2026-10-05 [claude]: Edit test_reindex_dispatch.py
- 2026-10-05 [claude]: commit fd4d729b68 — style(graph_os): format the library fan-in test
- 2026-10-05 [claude]: Edit test_reindex_dispatch.py
- 2026-10-05 [claude]: Edit test_reindex_dispatch.py
- 2026-10-05 [claude]: Edit reindex_dispatch.py
- 2026-10-05 [claude]: Edit reindex_dispatch.py
- 2026-10-05 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-05 [claude]: commit ec0df7ac61 — fix(graph_os): record an indexed doc as in sync, not as a failed reindex
- 2026-10-05 [claude]: Edit _reindex_routing.py
- 2026-10-05 [claude]: Edit _reindex_routing.py
- 2026-10-05 [claude]: Edit reindex_dispatch.py
- 2026-10-05 [claude]: Edit reindex_dispatch.py
- 2026-10-05 [claude]: Edit reindex_dispatch.py
- 2026-10-05 [claude]: Edit reindex_dispatch.py
- 2026-10-05 [claude]: Edit test_reindex_dispatch.py
- 2026-10-05 [claude]: Edit _reindex_on_edit.sh
- 2026-10-05 [claude]: Edit _reindex_on_edit.sh
- 2026-10-05 [claude]: Edit auto-reindex-graph.sh
- 2026-10-05 [claude]: Edit auto-reindex-docs.sh
- 2026-10-05 [claude]: Edit registry.yaml
- 2026-10-05 [claude]: Edit test_reindex_hook_suffixes.py
- 2026-10-05 [claude]: Edit test_reindex_hook_suffixes.py
- 2026-10-05 [claude]: Edit test_hooks_env_shape.py
- 2026-10-05 [claude]: Edit test_auto_reindex.py
- 2026-10-05 [claude]: Edit test_reindex_on_edit_hooks.py
- 2026-10-05 [claude]: Edit graph-use-cases.md
- 2026-10-05 [claude]: Edit polyglot-extractor-roadmap.md
- 2026-10-05 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-05 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-05 [claude]: commit 3a928d4d51 — fix(hooks): reindex each layer from its own module and index the last edit of a burst
- 2026-10-05 [claude]: Edit test_mcp_tools_impact.py
- 2026-10-05 [claude]: commit a50a55d0f6 — docs(skills): route clones, undefined names and library fan-in through graph-explorer
- 2026-10-05 [claude]: Edit _graph_references.py
- 2026-10-05 [claude]: Edit _graph_references.py
- 2026-10-05 [claude]: Edit _graph_references.py
- 2026-10-05 [claude]: Edit test_mcp_tools_impact.py
- 2026-10-05 [claude]: Edit _tools_graph_query.py
- 2026-10-05 [claude]: Edit _tools_graph_query.py
- 2026-10-05 [claude]: Edit _graph_cli_query.py
- 2026-10-05 [claude]: Edit _graph_cli_query.py
- 2026-10-05 [claude]: Edit graph_os-queries.md
- 2026-10-05 [claude]: Edit SKILL.md
- 2026-10-05 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-05 [claude]: commit cd4e0d2db8 — feat(graph_os): page cos_graph_references with an offset past the token-budget trim
- 2026-10-05 [claude]: CC-13/CC-16/CC-09 closed: docs-layer status fix (ec0df7ac, every doc reindex had stored an error), per-module reindex…
- 2026-10-07 [claude]: Edit test_go_implements.py
- 2026-10-07 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-07 [claude]: Edit _go_uids.py
- 2026-10-07 [claude]: Edit _go_uids.py
- 2026-10-07 [claude]: Edit _go_symbols.py
- 2026-10-07 [claude]: Edit _go_symbols.py
- 2026-10-07 [claude]: Edit _go_types.py
- 2026-10-07 [claude]: Edit _go_types.py
- 2026-10-07 [claude]: Edit _go_types.py
- 2026-10-07 [claude]: Edit _go_types.py
- 2026-10-07 [claude]: Edit _sqlite_links_go_implements.py
- 2026-10-07 [claude]: Edit _graph_references.py
- 2026-10-07 [claude]: Edit sqlite_backend.py
- 2026-10-07 [claude]: Edit sqlite_backend.py
- 2026-10-07 [claude]: Edit _sqlite_links.py
- 2026-10-07 [claude]: Edit _reindex_routing.py
- 2026-10-07 [claude]: Edit code_go.py
- 2026-10-07 [claude]: Edit code_go.py
- 2026-10-07 [claude]: Edit test_code_go.py
- 2026-10-07 [claude]: Edit _graph_cli_reindex.py
- 2026-10-07 [claude]: commit 453428a0de — style(graph_os): format the Go cross-file link tests
- 2026-10-07 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-07 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-07 [claude]: Edit graph_os-queries.md
- 2026-10-07 [claude]: Edit test_python_inherited_calls.py
- 2026-10-07 [claude]: Edit test_python_inherited_calls.py
- 2026-10-07 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-07 [claude]: Edit _python_resolve.py
- 2026-10-07 [claude]: Edit _python_emit.py
- 2026-10-07 [claude]: Edit _sqlite_links_py_inherited.py
- 2026-10-07 [claude]: Edit sqlite_backend.py
- 2026-10-07 [claude]: Edit sqlite_backend.py
- 2026-10-07 [claude]: Edit _sqlite_links.py
- 2026-10-07 [claude]: Edit _python_visitor.py
- 2026-10-07 [claude]: Edit _reindex_routing.py
- 2026-10-07 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-07 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-07 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-07 [claude]: Edit test_go_mod.py
- 2026-10-07 [claude]: Edit code_gomod.py
- 2026-10-07 [claude]: Edit code_gomod.py
- 2026-10-07 [claude]: Edit _reindex_routing.py
- 2026-10-07 [claude]: Edit _reindex_routing.py
- 2026-10-07 [claude]: Edit _reindex_layers.py
- 2026-10-07 [claude]: Edit _reindex_layers.py
- 2026-10-07 [claude]: Edit types.py
- 2026-10-07 [claude]: Edit base.py
- 2026-10-07 [claude]: Edit code_go.py
- 2026-10-07 [claude]: Edit _go_package.py
- 2026-10-07 [claude]: Edit _go_package.py
- 2026-10-07 [claude]: Edit _graph_undefined.py
- 2026-10-07 [claude]: Edit _graph_undefined.py
- 2026-10-07 [claude]: Edit _graph_undefined.py
- 2026-10-07 [claude]: Edit auto-reindex-graph.sh
- 2026-10-07 [claude]: Edit _graph_export.py
- 2026-10-07 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-07 [claude]: commit 5142dbe2ca — feat(graph_os): index go.mod requires and report undeclared and unused Go modules
- 2026-10-07 [claude]: Edit test_go_fiber_cross_file.py
- 2026-10-07 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-07 [claude]: Edit _go_routes.py
- 2026-10-07 [claude]: Edit _go_routes.py
- 2026-10-07 [claude]: Edit _go_routes.py
- 2026-10-07 [claude]: Edit _go_routes.py
- 2026-10-07 [claude]: Edit _go_routes.py
- 2026-10-07 [claude]: Edit _go_routes.py
- 2026-10-07 [claude]: Edit _go_routes.py
- 2026-10-07 [claude]: Edit test_go_fiber_routes.py
- 2026-10-07 [claude]: Edit _sqlite_links_routes.py
- 2026-10-07 [claude]: Edit _sqlite_links_routes.py
- 2026-10-07 [claude]: Edit _sqlite_links_routes.py
- 2026-10-07 [claude]: GO-09 (ead0480c): Go interface methods are nodes + structural implements link pass (benchmark 0 -> 174 edges, 60/61…
- 2026-10-07 [claude]: commit 3b3674f368 — fix(graph_os): compose Fiber route prefixes passed in from another file or package
- 2026-10-07 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-07 [claude]: Edit pytest-piped-to-tail-hides-failures.md
- 2026-10-07 [claude]: Edit resume-after-pause-refresh-markers.md
- 2026-10-07 [claude]: commit f59481c034 — docs(graph_os): replace dashes in the audit answers and the new link-pass docstrings
- 2026-10-07 [claude]: Edit harness.py
- 2026-10-07 [claude]: Edit p_fiber.py
- 2026-10-07 [claude]: Edit p_fiber2.py
- 2026-10-07 [claude]: Edit p_fiber3.py
- 2026-10-07 [claude]: Edit p_pyinh.py
- 2026-10-07 [claude]: Edit p_pysuper.py
- 2026-10-07 [claude]: Edit p_pymro.py
- 2026-10-07 [claude]: Edit p_goimpl.py
- 2026-10-07 [claude]: Edit p_godead.py
- 2026-10-07 [claude]: Edit p_gomod.py
- 2026-10-07 [claude]: Edit p_hook.sh
- 2026-10-07 [claude]: Edit p_consumer.sh
- 2026-10-07 [claude]: Edit p_arity.py
- 2026-10-07 [claude]: commit faf79f5889 — fix(hooks): find the reindex body and core through the real hook path in consumer projects
- 2026-10-07 [claude]: Edit _sqlite_links_go.py
- 2026-10-07 [claude]: Edit _reindex_layers.py
- 2026-10-07 [claude]: Edit _sqlite_links_routes.py
- 2026-10-07 [claude]: Edit _sqlite_links_py_inherited.py
- 2026-10-07 [claude]: Independent review of the GO-07/09/10, PY-15, CC-13 commits confirmed 10 defects; all fixed with regression tests…
- 2026-10-07 [claude]: Status transitioned to complete via cos task-done.
