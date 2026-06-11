---
id: TASK-395
title: "Graph build hygiene v2 \u2014 symlink-aware links, dead-stub GC, loud bounded reindex, honest severity"
swimlane: "graph_os"
kind: bug
epic: null
labels: [graph-os, hygiene, doctor, reindex, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-11
started: 2026-06-11
completed: 2026-06-11
agent_session: ses-claude-20260610-185418-2b3f
depends_on: []
blocked_by: []
references: []
---
# TASK-395: Graph build hygiene v2 — symlink-aware links, dead-stub GC, loud bounded reindex, honest severity

---
id: TASK-395
title: "Graph build hygiene v2 — symlink-aware links, dead-stub GC, loud bounded reindex, honest severity"
swimlane: "graph_os"
kind: bug
epic: null
labels: [graph-os, hygiene, doctor, reindex, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-06-11
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-395: Graph build hygiene v2 — symlink-aware links, dead-stub GC, loud bounded reindex, honest severity

**Outcome (one sentence):** cos_graph_doctor reports healthy=true with ZERO real issues and the Hub badge agrees: links to in-repo symlinks (CLAUDE.md) resolve to their real target instead of re-minting a malformed node; doctor fix=True garbage-collects zero-edge external/identifier stubs left by deleted files (2,099 today); parallel graph-reindex can never stall silently (graph-layer write failures counted+echoed as errors, lock waits bounded to seconds not 30s); files whose bash -n passes no longer count tree-sitter grammar gaps as parse_errors; doctor stats.issue_count counts only real categories.

## Read First
- src/core/graph_os/extractors/md_links.py
- src/core/graph_os/tools/graph.py
- src/core/graph_os/tools/reindex_dispatch.py
- src/cli/graph_commands.py
- src/core/graph_os/extractors/code_shell.py
- docs/playbooks/polyglot-extractor-roadmap.md

## Repro Steps
1. After TASK-393's cleanup, edit any doc linking `[CLAUDE.md](CLAUDE.md)` (root symlink → AGENTS.md) — auto-reindex re-mints `doc:file:CLAUDE.md`; doctor flags malformed_uid_path=1, healthy=false (observed 2026-06-11 Hub screenshot).
2. Delete a source file (e.g. the removed Hub AuditsPage) — its `code:external:*` import stubs have file_path=NULL so neither per-file prune, full-walk reconcile, nor doctor fix removes them; dead zero-edge stubs accumulate (2,099 of 9,099 today).
3. Hold a write transaction open on coding-os.db, run `cos graph-reindex --force -j 4` over docs/tasks — every statement blocks 30 s (backend busy_timeout), 3 retries/file, per-file failure lands only in `layers.graph.status` which the CLI counts as PROCESSED: zero rows written, zero errors echoed, looks hung (2026-06-11 stall, 23 idle workers/15 min).
4. Doctor shows files_with_parse_errors=3 for valid-bash hooks (`$((10#…))`, `${V:+ (…)}`, concatenated case patterns) — tree-sitter grammar gaps counted as file errors; Hub ISSUES badge counts info categories.
Expected: none of the four. Actual: all four.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a doc linking to an in-repo symlink (CLAUDE.md), **When** md_links/task_deps extract it, **Then** the edge lands on the symlink's resolved target (doc:file:AGENTS.md) and no node with the symlink path is minted.
- **Given** zero-edge `code:external:*`/`cos:identifier:*` stubs, **When** `cos_graph_doctor(fix=True)` runs, **Then** they are deleted (re-mint on next reference) and the category is listed in fixable_categories.
- **Given** a write lock held by another process, **When** parallel reindex runs, **Then** each file fails loudly within seconds (bounded busy wait), the CLI errors counter + stderr show the lock reason, and the summary never reports a silent all-processed run.
- **Given** a shell file where `bash -n` succeeds but tree-sitter reports ERROR nodes, **When** it is indexed, **Then** parse_errors_count stays 0 (grammar gap recorded as metadata, real syntax errors still counted).
- **Given** the fixes, **When** doctor runs after a fresh reindex, **Then** healthy=true, stats.issue_count counts real categories only, and targeted tests + the full graph suite are green.

## Work Log
- 2026-06-11 [claude]: Edit polyglot-extractor-roadmap.md
- 2026-06-11 [claude]: Edit mcp-error-envelope.md
- 2026-06-11 [claude]: Edit mcp-error-envelope.md
- 2026-06-11 [claude]: Edit md_links.py
- 2026-06-11 [claude]: Edit md_links.py
- 2026-06-11 [claude]: Edit md_links.py
- 2026-06-11 [claude]: Edit task_deps.py
- 2026-06-11 [claude]: Edit task_deps.py
- 2026-06-11 [claude]: Edit graph.py
- 2026-06-11 [claude]: Edit graph.py
- 2026-06-11 [claude]: Edit graph.py
- 2026-06-11 [claude]: Edit graph.py
- 2026-06-11 [claude]: Edit graph_commands.py
- 2026-06-11 [claude]: Edit graph_commands.py
- 2026-06-11 [claude]: Edit code_shell.py
- 2026-06-11 [claude]: Edit code_shell.py
- 2026-06-11 [claude]: Edit code_shell.py
- 2026-06-11 [claude]: Edit code_shell.py
- 2026-06-11 [claude]: Edit graph_commands.py
- 2026-06-11 [claude]: Edit graph_commands.py
- 2026-06-11 [claude]: Edit test_md_links.py
- 2026-06-11 [claude]: Edit test_md_links.py
- 2026-06-11 [claude]: Edit test_task_deps.py
- 2026-06-11 [claude]: Edit test_centrality_ranking_doctor.py
- 2026-06-11 [claude]: Edit code_shell.py
- 2026-06-11 [claude]: Edit code_shell.py
- 2026-06-11 [claude]: Edit code_shell.py
- 2026-06-11 [claude]: Edit task_deps.py
- 2026-06-11 [claude]: Edit reindex_dispatch.py
- 2026-06-11 [claude]: Edit reindex_dispatch.py
- 2026-06-11 [claude]: Edit reindex_dispatch.py
- 2026-06-11 [claude]: Edit reindex_dispatch.py
- 2026-06-11 [claude]: Edit reindex_dispatch.py
- 2026-06-11 [claude]: Edit reindex_dispatch.py
- 2026-06-11 [claude]: Edit reindex_dispatch.py
- 2026-06-11 [claude]: Edit reindex_dispatch.py
- 2026-06-11 [claude]: Edit graph_commands.py
- 2026-06-11 [claude]: Edit reindex_dispatch.py
- 2026-06-11 [claude]: Edit reindex_dispatch.py
- 2026-06-11 [claude]: Edit graph_commands.py
- 2026-06-11 [claude]: Edit graph_commands.py
- 2026-06-11 [claude]: Edit graph_commands.py
- 2026-06-11 [claude]: Edit graph_commands.py
- 2026-06-11 [claude]: All five fixes landed: symlink-aware link resolution (md_links/_resolve_through_symlink + task_deps), dead-stub GC in do
- 2026-06-11 [claude]: Status transitioned to complete via cos task-done.
