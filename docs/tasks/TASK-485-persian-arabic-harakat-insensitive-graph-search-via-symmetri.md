---
id: TASK-485
title: "Persian/Arabic harakat-insensitive graph search via symmetric Python normalization (write + query path)"
swimlane: "graph_os"
kind: feature
epic: null
labels: [i18n, fts5, ready]
status: in_progress
priority: P3
appetite: 1d
created: 2026-06-20
started: 2026-06-20
completed: null
agent_session: ses-claude-20260620-144553-a8b6
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
