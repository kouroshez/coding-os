---
id: TASK-485
title: "Persian/Arabic harakat-insensitive graph search via symmetric Python normalization (write + query path)"
swimlane: "graph_os"
kind: feature
epic: null
labels: [i18n, fts5, ready]
status: archive
priority: P3
appetite: 1d
created: 2026-06-20
started: 2026-06-20
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-485: Persian/Arabic harakat-insensitive graph search via symmetric Python normalization (write + query path)

**Outcome (one sentence):** cos_graph_search / cos_graph_resolve match Persian/Arabic identifiers and docstrings whether or not harakat (U+064B–U+0652, U+0670) are present, via symmetric Python normalization at the FTS write path and query path — NOT an FTS schema migration. Prioritize only if Persian/Arabic docstring search is a named launch market; the unproven v29 "remove_diacritics" fix does NOT fold Arabic harakat (verified live) and its test passes vacuously.

## Read First
- src/core/graph_os/tools/graph.py
- src/core/thinking_os/database.py
- src/core/graph_os/bench/persian_precision.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** SQLite FTS5 'unicode61 remove_diacritics 2' folds only Latin combining marks and NOT Arabic/Persian harakat (functionally verified), **When** a node label/signature/doc_blob is indexed into graph_nodes_fts and when a query passes through _fts5_safe_query (graph.py:5423), **Then** both apply identical NFKD + harakat-strip (U+064B–U+0652, U+0670) normalization so a harakat-free query matches a harakat-bearing form and vice-versa. **And** one real (non-vacuous) folding test asserts the cross-form match. **And** no schema migration is introduced (pure Python normalization). **And** the fresh-install DDL at database.py:760 has its graph_nodes_fts tokenize changed from 'porter unicode61' to match v29 ('unicode61 remove_diacritics 2'), so a new DB is never momentarily born on the porter tokenizer before v29 runs; no migration is added for existing DBs.

## Work Log
- 2026-06-20 [claude]: Edit graph.py
- 2026-06-20 [claude]: Edit test_mcp_tools.py
- 2026-06-20 [claude]: Shipped query-side harakat folding: _fold_harakat() + applied in _fts5_safe_query (graph.py) strips U+064B–U+0652 +…
- 2026-06-20 [claude]: committed 9dbd0bd5 · 2 files
- 2026-08-02 [claude]: Archive triage 2026-08-02 (investigated to the mechanism): graph_nodes_fts is EXTERNAL-CONTENT (content=graph_nodes),…
- 2026-08-02 [claude]: Edit pyproject.toml
- 2026-08-02 [claude]: commit ec1f6078ab — build: pin ruff==0.15.15 — floating pin broke the CI format gate on each release
- 2026-08-02 [claude]: Edit icebox-parking-structural-failure.md
- 2026-08-02 [claude]: commit d97eee55ed — docs(api): regenerate openapi.json — spec drifted from live routes
- 2026-08-02 [claude]: Edit test_mcp_tools.py
- 2026-08-02 [claude]: Edit test_mcp_tools.py
- 2026-08-02 [claude]: commit 2fdf517b25 — test(ci): recapture goldens + manifest; probe real model in graph embedding tests
- 2026-08-02 [claude]: Edit conftest.py
- 2026-08-02 [claude]: commit 10a17fadca — test(ci): ignore golden fixtures at collection + restore gitignore-swallowed changes.log
- 2026-08-02 [claude]: Edit generate_manifest.py
- 2026-08-02 [claude]: Edit capture_golden.py
- 2026-08-02 [claude]: commit 85979f7914 — fix(ci): exclude .ruff_cache from manifest + golden capture — dev-cache pollution
- 2026-08-02 [claude]: Edit test_hook_registry_integration.py
- 2026-08-02 [claude]: Edit _pre_commit_body.sh
- 2026-08-02 [claude]: Edit _pre_commit_body.sh
- 2026-08-02 [claude]: commit 416148fec1 — fix(ci): resolve adapter-scoped hooks in registry test + drop herestring read-loop
- 2026-08-02 [claude]: commit 0b05077b86 — style: ruff format on the registry-test edit
- 2026-08-03 [claude]: Edit test_branding.py
- 2026-08-03 [claude]: commit 677abfe441 — test: allow descriptive Claude Code reference in SettingsPage auth help
