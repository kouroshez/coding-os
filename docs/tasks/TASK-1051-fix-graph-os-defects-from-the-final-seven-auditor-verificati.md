---
id: TASK-1051
title: "Fix graph_os defects from the final seven-auditor verification round (V-01..V-52)"
swimlane: "graph_os"
kind: bug
epic: null
labels: [ready, docs-update]
status: complete
priority: P1
appetite: 3d
created: 2026-10-07
started: 2026-10-07
completed: 2026-10-07
agent_session: ses-claude-20261007-140442-890a
depends_on: []
blocked_by: []
references: []
---
# TASK-1051: Fix graph_os defects from the final seven-auditor verification round (V-01..V-52)

**Outcome (one sentence):** Every confirmed defect in the final-round register is fixed with a regression test and committed, highest severity first, starting with the stub-edge freshness root cause (V-01) that loses callers on rename, move and delete.

## Read First
- docs/engineering/graph-os-polyglot-audit-2026-10-07-final-round.md
- docs/engineering/graph-os-polyglot-audit-2026-10-04.md
- docs/engineering/graph_os-queries.md

## Repro Steps
See the register: each item names the auditor probe under scratchpad/agents/<member>/final/ that reproduces it; V-01 repro is graph-completeness-auditor/final/p3_incremental.py and p20_bench_move.py.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the register docs/engineering/graph-os-polyglot-audit-2026-10-07-final-round.md, **When** an item is fixed, **Then** it is marked [x] with its fix and test name and committed on its own.
- **Given** a renamed, moved or deleted symbol or file, **When** the graph is relinked without --force, **Then** callers in other files keep or regain their edges (V-01, V-02).
- **Given** the graph_os, thinking_os and CLI verification-matrix suites, **When** the round closes, **Then** all are green and make lint passes.

## Work Log
- 2026-10-07 [claude]: commit c9db09ecae — docs(graph_os): register the 52 defects the seven-auditor final round confirmed
- 2026-10-07 [claude]: Edit test_relink_after_edits.py
- 2026-10-07 [claude]: Edit _sqlite_write.py
- 2026-10-07 [claude]: Edit _sqlite_write.py
- 2026-10-07 [claude]: Edit _sqlite_links.py
- 2026-10-07 [claude]: Edit test_ts_cross_file_links.py
- 2026-10-07 [claude]: Edit _graph_cli_reindex.py
- 2026-10-07 [claude]: Edit _graph_cli_reindex.py
- 2026-10-07 [claude]: commit 792313b974 — fix(graph_os): re-read a pruned node's dependents and relink the callers of names a file gains
- 2026-10-07 [claude]: Edit _reindex_on_edit.sh
- 2026-10-07 [claude]: commit 24c5c47809 — fix(graph_os): count renders and calls through variables in default references
- 2026-10-07 [claude]: Edit test_contracts_paging.py
- 2026-10-07 [claude]: Edit _tools_graph_insights.py
- 2026-10-07 [claude]: Edit _graph_cli_query.py
- 2026-10-07 [claude]: Edit graph-os-polyglot-audit-2026-10-07-final-round.md
- 2026-10-07 [claude]: Edit graph_os-queries.md
- 2026-10-07 [claude]: Edit backend.py
- 2026-10-07 [claude]: Edit _graph_walk.py
- 2026-10-07 [claude]: Edit _graph_walk.py
- 2026-10-07 [claude]: Edit _sqlite_read.py
- 2026-10-07 [claude]: Edit _graph_references.py
- 2026-10-07 [claude]: Edit _graph_references.py
- 2026-10-07 [claude]: Edit _graph_references.py
- 2026-10-07 [claude]: Edit _graph_references.py
- 2026-10-07 [claude]: Edit _graph_walk.py
- 2026-10-07 [claude]: commit 7a06d8273b — fix(graph_os): read every contract registration and page it by scope, offset and limit
- 2026-10-07 [claude]: commit 783d400cf0 — fix(graph_os): count a file's dependents through every node it defines, not only its module
- 2026-10-07 [claude]: Edit _sqlite_links.py
- 2026-10-07 [claude]: Edit _sqlite_links.py
- 2026-10-07 [claude]: Edit _sqlite_links.py
- 2026-10-07 [claude]: Edit _reindex_layers.py
- 2026-10-07 [claude]: commit 1256030130 — fix(graph_os): bind from-package imports of a submodule to its file, also at edit time
- 2026-10-07 [claude]: V-08 (7a06d827): contracts read every handles_* edge, scope = path prefix, offset/limit paging + total_count; bench…
- 2026-10-07 [claude]: commit 2edf3937ad — test(graph_os): pin that a route two services register survives one of them leaving
- 2026-10-07 [claude]: Edit _python_visitor.py
- 2026-10-07 [claude]: Edit _python_visitor.py
- 2026-10-07 [claude]: Edit _python_visitor.py
- 2026-10-07 [claude]: Edit _python_visitor.py
- 2026-10-07 [claude]: Edit _python_visitor.py
- 2026-10-07 [claude]: Edit _reindex_routing.py
- 2026-10-07 [claude]: commit ed3194482b — fix(graph_os): link FastAPI dependencies named in annotations, aliases and module attributes
- 2026-10-07 [claude]: Edit test_go_member_calls.py
- 2026-10-07 [claude]: Edit _go_receivers.py
- 2026-10-07 [claude]: commit 9e1038a078 — feat(graph_os): resolve Go method calls through the declared type of their receiver
- 2026-10-07 [claude]: V-07 (2edf3937): shared route survives one registrant leaving — already healed by V-01's dependent refresh; uid kept…
- 2026-10-07 [claude]: Edit test_astro_template.py
- 2026-10-07 [claude]: V-34: TS class expressions named by holder (const X = class → class X; mixin → F.class), 149/149 bench methods (0…
- 2026-10-07 [claude]: Edit _reindex_on_edit.sh
- 2026-10-07 [claude]: Edit _analysis_impact.py
- 2026-10-07 [claude]: Edit _graph_references.py
- 2026-10-07 [claude]: commit 9c7ad2e950 — feat(graph_os): page impact and duplicates past the token budget with offset
- 2026-10-07 [claude]: MEDIUM/LOW sweep: V-05 deleted file forgets all cache rows (restore reindexes). V-06 shell reconcile hook → one…
- 2026-10-07 [claude]: commit 85611b9011 — fix(graph_os): keep declared Python dependencies off same-named repo files, drop self-loops
- 2026-10-07 [claude]: Edit _sqlite_write.py
- 2026-10-07 [claude]: Edit _sqlite_write.py
- 2026-10-07 [claude]: Edit _sqlite_write.py
- 2026-10-07 [claude]: commit f601f90ed7 — fix(graph_os): bind names destructured from a TS dynamic import like an import
- 2026-10-07 [claude]: V-29 self.attr.m() no longer own method (v33). V-35 TS member chains kept whole; X.m() keyed by export only for…
- 2026-10-07 [claude]: commit e8b5ea5c8f — fix(graph_os): index Python defs under compound statements and bind class, star and submodule calls
- 2026-10-07 [claude]: Edit _graph_undefined_deps.py
- 2026-10-07 [claude]: commit 42f1cdedca — feat(graph_os): report undeclared npm and Python dependencies and unused npm dependencies
- 2026-10-07 [claude]: V-24 Go not_imported (package-wide check) + grouped var blocks indexed (bench +174 vars), 0 FP, v40. V-12 FastAPI…
- 2026-10-07 [claude]: commit 14375bdd2b — fix(graph_os): read file-route forms: underscore folders, compound params, md pages, re-exports
- 2026-10-07 [claude]: commit d09cdcb63f — fix(graph_os): resolve Go local replaces and count in-repo sibling module imports as used
- 2026-10-07 [claude]: commit e7e5623baf — fix(graph_os): keep literals in a data table's clone fingerprint so same-shaped tables are no copy
- 2026-10-07 [claude]: commit be7596ae3d — fix(graph_os): resolve TS project references, fallthrough exports, workspace presets and # imports
- 2026-10-07 [claude]: commit f7363275c2 — fix(graph_os): walk only included files and keep build-named folders git tracks
- 2026-10-07 [claude]: Edit test_shell_forms.py
- 2026-10-07 [claude]: Edit auto-reindex-graph.sh
- 2026-10-07 [claude]: Edit auto-reindex-docs.sh
- 2026-10-07 [claude]: commit 00ced376d6 — fix(graph_os): read shell script-dir idioms and run forms, report lost shell functions
- 2026-10-07 [claude]: Edit test_astro_scripts.py
- 2026-10-07 [claude]: commit 059999f4da — fix(graph_os): scope Astro client scripts, read only processed ones and import script src
- 2026-10-07 [claude]: Edit test_ts_reexports.py
- 2026-10-07 [claude]: commit 7b79e6a599 — fix(graph_os): follow renamed TS re-exports, find barrel cycles, link platform twins
- 2026-10-07 [claude]: Edit test_go_resolution.py
- 2026-10-07 [claude]: commit ae21298b23 — fix(graph_os): resolve Go shadowing, generics, package clauses, several init and build-tag twins
- 2026-10-07 [claude]: Edit test_go_implements_precision.py
- 2026-10-07 [claude]: commit eba1fcf2e3 — fix(graph_os): compare Go method signatures, ambiguous promotion and package clauses for implements
- 2026-10-07 [claude]: Edit test_python_scope_edges.py
- 2026-10-07 [claude]: Edit _undefined_python.py
- 2026-10-07 [claude]: commit dd8e602352 — fix(graph_os): stop Python module-level double counting and scope annotation names
- 2026-10-07 [claude]: Round close: V-23,V-25,V-26,V-32,V-37,V-39,V-44,V-48,V-49,V-51 + V-50 literal half fixed (extraction v48→56), each…
- 2026-10-07 [claude]: Correction: the per-call scan cost behind the V-50 deferral was an estimate (5-10 s); measured, hashing every…
- 2026-10-07 [claude]: Edit _graph_fragments.py
- 2026-10-07 [claude]: Edit _go_scopes.py
- 2026-10-07 [claude]: commit e574e918c0 — fix(graph_os): scope Go locals by position, skip generator package clauses, match builtin aliases
- 2026-10-07 [claude]: Close: V-50 fragment half shipped (fragments=true, 166/210 groups in ~1.8 s); independent review found 11 defects +…
- 2026-10-07 [claude]: Status transitioned to complete via cos task-done.
