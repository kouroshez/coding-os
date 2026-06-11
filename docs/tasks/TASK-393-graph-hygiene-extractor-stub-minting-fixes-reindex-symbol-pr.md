---
id: TASK-393
title: "Graph hygiene \u2014 extractor stub-minting fixes, reindex symbol prune, one-time orphan cleanup"
swimlane: "graph_os"
kind: bug
epic: null
labels: [graph-os, hygiene, doctor, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-11
started: 2026-06-11
completed: 2026-06-11
agent_session: ses-claude-20260610-185418-2b3f
depends_on: []
blocked_by: []
references: []
---
# TASK-393: Graph hygiene — extractor stub-minting fixes, reindex symbol prune, one-time orphan cleanup

---
id: TASK-393
title: "Graph hygiene — extractor stub-minting fixes, reindex symbol prune, one-time orphan cleanup"
swimlane: "graph_os"
kind: bug
epic: null
labels: [graph-os, hygiene, doctor, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-11
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-393: Graph hygiene — extractor stub-minting fixes, reindex symbol prune, one-time orphan cleanup

**Outcome (one sentence):** cos_graph_doctor reports healthy=true (only info-severity categories remain): task_deps no longer mints doc:file stubs from bare names/URLs/junk, md_links drops nonexistent .md targets, incremental reindex prunes nodes for symbols removed from a file, and the 33 legacy orphans (golden leftovers, deleted TSX symbols, stale headings, phantom modules, CLAUDE.md symlink) are purged without re-minting on the next reindex.

## Read First
- src/core/graph_os/extractors/task_deps.py
- src/core/graph_os/extractors/md_links.py
- src/core/graph_os/tools/graph.py
- docs/playbooks/polyglot-extractor-roadmap.md
- docs/engineering/graph-hallucination-cures.md

## Repro Steps
1. Run cos_graph_doctor on the meta-repo (2026-06-11 state).
2. Observe healthy=false with stale_paths=74 (doc:file stubs for `SKILL.md`, `//github.com/...`, moved ADR/_meta paths), orphaned_inrepo=30 (20 tests/golden leftovers, 7 deleted TSX symbols, 2 removed doc headings), orphaned_phantom=2 (extract_intent, web.routes.audits), malformed_uid_path=1 (CLAUDE.md symlink).
3. Run doctor fix=True, then reindex docs/tasks — stale stubs re-mint (delete↔reindex churn).
Expected: healthy=true and stays true after a full reindex.
Actual: healthy=false; fix=True only papers over extractor-minted stubs.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a task file whose Read First bullets contain a bare doc name (`SKILL.md`), a URL (`https://github.com/.../api-reference.md`), and a real repo-rooted doc path, **When** task_deps extracts it, **Then** only the existing repo-rooted path mints a references_doc edge; bare names and URL fragments are dropped.
- **Given** a markdown doc linking to a nonexistent `.md` path, **When** md_links resolves the link, **Then** no doc:file stub node is minted (same drop policy as extensionless targets).
- **Given** a file indexed with symbol S, **When** S is removed from the file and the file is reindexed incrementally, **Then** S's node row is deleted from graph_nodes (no zero-edge ghost remains).
- **Given** the post-fix graph, **When** legacy orphans are purged once and `cos_graph_doctor` runs after a fresh reindex, **Then** healthy=true with only info-severity categories (external stubs, parse errors, slow extractions).
- **Given** the targeted new tests plus the full graph suite (`uv run --extra graph_os pytest src/core/graph_os/tests/ -q`), **When** run, **Then** all green.

## Work Log
- 2026-06-11 [claude]: Edit polyglot-extractor-roadmap.md
- 2026-06-11 [claude]: Edit task_deps.py
- 2026-06-11 [claude]: Edit md_links.py
- 2026-06-11 [claude]: Edit md_links.py
- 2026-06-11 [claude]: Edit __init__.py
- 2026-06-11 [claude]: Edit graph.py
- 2026-06-11 [claude]: Edit graph.py
- 2026-06-11 [claude]: Edit graph.py
- 2026-06-11 [claude]: Edit test_task_deps.py
- 2026-06-11 [claude]: Edit test_task_deps.py
- 2026-06-11 [claude]: Edit test_md_links.py
- 2026-06-11 [claude]: Edit test_md_links.py
- 2026-06-11 [claude]: Edit test_md_links.py
- 2026-06-11 [claude]: Edit test_centrality_ranking_doctor.py
- 2026-06-11 [claude]: Edit test_centrality_ranking_doctor.py
- 2026-06-11 [claude]: Edit mcp-error-envelope.md
- 2026-06-11 [claude]: Edit mcp-error-envelope.md
- 2026-06-11 [claude]: Existence gate landed in md_links (_resolve_link + _resolve_read_target) and task_deps (_extract_doc_paths); doctor _is_
- 2026-06-11 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-11 [claude]: committed 1fe63fbc: docs/engineering/mcp-error-envelope.md, docs/playbooks/polyglot-extractor-roadmap.md, src/core/graph
