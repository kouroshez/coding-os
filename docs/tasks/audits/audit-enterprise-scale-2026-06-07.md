<!-- domain:META | layer:audit | ssot:true | updated:2026-06-07 -->
# Audit — Enterprise Scale Hardening (10K-100K+ tasks / commits / nodes)

> Nav: [docs/tasks/audits/](./00-index.md) · epic [TASK-222](../TASK-222-epic-enterprise-scale-hardening-system-must-not-break-agent-.md)

status: in_progress
phase: discovery-complete · remediation-pending

Purpose: SSOT of every scale-breaker found by the 8-module parallel audit (workflow whs0yre8t, 45 agents). The system MUST not break — agent, CLI, or panel — at 10K-100K+ tasks/commits.
Read when: pulling a child task of the scale-hardening epic.

## Summary — 73 findings (8 critical · 29 high · 36 med · 0 low); 8 adversarially-verified critical/high

| Module | Verdict | Findings |
|---|---|---|
| src/core/board_os/** - Scrumban task board, SQL querie | **breaks** | 11 |
| src/core/web/routes/** (FastAPI endpoints) + src/core/ | **breaks** | 14 |
| src/core/thinking_os/** (memory, observations, learnin | **breaks** | 7 |
| src/core/graph_os/** (nodes/edges, extractors, export, | **breaks** | 11 |
| src/cli/** CLI commands (cos board, cos daily, cos doc | **breaks** | 9 |
| RAG/Embeddings/Doc Indexer (src/core/thinking_os/embed | **breaks** | 7 |
| git/commit operations at 100K-1M commits scale | **breaks** | 7 |
| src/core/hooks/** per-tool-call overhead at scale (100 | **breaks** | 7 |

## Findings by module (critical + high)

### src/core/board_os/** - Scrumban task board, SQL queries, pagination
| Sev | Location | Issue | Breaks at | Fix |
|---|---|---|---|---|
| high | `src/core/board_os/mcp_tools.py:1743` | Unbounded icebox query in cos_task_daily fetches ALL icebox tasks with no LIMIT | 10K icebox tasks | Add LIMIT to icebox query and paginate with cursor-based pagination if the UI needs the full list. For daily r |
| high | `src/core/board_os/mcp_tools.py:1734-1742` | cos_task_daily fetches all in_progress + testing + blocked tasks with no LIMIT | 10K tasks in-flight | Add a LIMIT to each status query: `LIMIT 200` for in_progress/testing/blocked. These are daily stand-up cards; |
| high | `src/core/board_os/mcp_tools.py:1612-1618` | Unbounded SELECT in _archive_stale_sweep scans entire status column for icebox + complete  | 50K+ aged tasks | Use a DATE-based keyset pagination or add an ORDER BY dwell_seconds DESC LIMIT to auto-archive only the oldest |
| high | `src/core/board_os/mcp_tools.py:1440-1443` | cos_task_reclaim fetches ALL in_progress + testing + emergency tasks with no LIMIT; then p | 100+ mid-flight tasks | Either: (A) Cap the reclaim scan to LIMIT 50 and stagger across multiple calls (e.g., per-swimlane), or (B) re |
| high | `src/core/board_os/mcp_tools.py:1543-1549` | cos_task_reconcile fetches ALL in_progress + testing + emergency tasks and calls _commits_ | 100+ mid-flight tasks | Add `LIMIT 100` to line 1543 query. If exhaustive reconciliation is needed, document that it runs in batches.  |

### src/core/web/routes/** (FastAPI endpoints) + src/core/web/ui/src/** (React SPA)
| Sev | Location | Issue | Breaks at | Fix |
|---|---|---|---|---|
| critical | `src/core/web/routes/observability.py:210` | UNBOUNDED FULL-FILE READ: _read_hook_events() calls hook_log.read_text().splitlines() with | 10K+ hook events (~5-10 MB hook  | Replace with bounded tail-read: seek to end, read last N KB (fixed 256 KB window like presence.py::_latest_tra |
| critical | `src/core/web/routes/observability.py:259-265` | UNBOUNDED DIRECTORY SCAN: _read_cognition_events() iterates ALL agent_dirs and globs ALL t | 100+ trace files across agents ( | Add a cap: glob only the last N files by mtime (e.g. last 50 traces per agent or 100 total), not all. Refactor |
| high | `src/core/web/routes/observability.py:91-176 (_sc` | FULL DIRECTORY TREE WALK: _scan_sessions() iterates state.iterdir() (all agents) → session | 10K+ sessions (50+ MB of session | Pagination: accept offset/limit params, return only [offset:offset+limit] rows. Pre-sort by (is_active DESC, m |
| high | `src/core/web/routes/board.py:344-366` | UNBOUNDED SESSION DIRECTORY SCAN: board_list() iterates ALL agents, reads EVERY presence f | 1000+ presence files per agent ( | Cache _presence_files() result + counts for 30s (signature: max(mtime) in sessions/). Limit to last N files by |
| high | `src/core/web/routes/presence.py:113` | UNBOUNDED PANEL DIRECTORY SCAN: _newest_marker() scans agent_dir/panels/ with panels.iterd | 100+ panel directories per agent | Cache panels/ list for 60s (keyed by agent, invalidate on dir mtime change). Alternatively: limit iterdir scan |
| high | `src/core/web/routes/cognition.py:236` | UNBOUNDED TRACE FILE READ: get_trace() calls target.read_text().splitlines() with NO size  | 1 GB+ trace file (e.g. a run_awa | Enforce a hard cap: read only last 1M events (or 256 MB, whichever comes first). Tail-read via seek-to-end app |
| high | `src/core/web/routes/observability.py:131-138` | FULL PRESENCE FILE SCAN IN LOOP: _load_presence_for_agent() called per agent in board.py l | 10K presence files per agent (10 | Cache per-agent presence glob result for 10s. Limit to last N files (e.g. 500) per agent. Batch load all agent |
| high | `src/core/web/routes/board.py:281 & graph.py:215` | limit parameter unbounded, board_list defaults to 2000, graph_export defaults to 2000 (lat | 100K tasks (board with limit=200 | Enforce hard ceiling: board_list max_limit=500, graph_export max_nodes=5000 (enforce via Query(max=5000)). Val |

### src/core/thinking_os/** (memory, observations, learning, metrics, cognition)
| Sev | Location | Issue | Breaks at | Fix |
|---|---|---|---|---|
| critical | `/Users/ciro/Files/Project/coding-os/src/core/thi` | Unbounded fetchall() over ALL learned_patterns without LIMIT. At 100K patterns, loads enti | 100K+ patterns | Implement keyset pagination with LIMIT 1000 per batch, process in transaction batches. Replace per-item UPDATE |
| high | `/Users/ciro/Files/Project/coding-os/src/core/thi` | O(n^2) duplicate consolidation pattern: nested SELECT + EXECUTEMANY for every (pattern, do | 1K+ duplicate groups | Use single CTE-based MERGE logic: WITH keepers AS (SELECT DISTINCT ON (pattern, domain) id FROM learned_patter |
| high | `/Users/ciro/Files/Project/coding-os/src/core/thi` | Type coercion on reviewer_check Literal field causes silent parse failures logged but not  | Any exhaustive intent task with  | Split: add separate reviewer_notes: str field to ExhaustiveEvidence for free-text feedback; keep reviewer_chec |

### src/core/graph_os/** (nodes/edges, extractors, export, query, reindex; scale target: 100K-1M nodes)
| Sev | Location | Issue | Breaks at | Fix |
|---|---|---|---|---|
| critical | `src/core/graph_os/tools/graph.py:3970-3973` | Unbounded edge enumeration in cos_graph_ranking at scale | 100K+ edges (1M+ edges in produc | Keyset the edge query: SELECT source_id, target_id FROM graph_edges_v12 WHERE source_id IN (node_ids) OR targe |
| high | `src/core/graph_os/tools/graph.py:841-850` | Inefficient JOIN with OR condition in _degree_map_for bypasses indexes | 10K-100K nodes (every export/que | Split into two indexed queries: UNION of (SELECT uid, COUNT(*) FROM graph_edges_v12 WHERE source_id IN (...) G |
| high | `src/core/graph_os/tools/graph.py:3466-3477` | Per-item list_edges calls inside loop for betweenness centrality — O(n) queries at scale | 300+ nodes (calls list_edges 300 | Batch the edge lookup: collect all node_ids, then SELECT source_id, target_id FROM graph_edges_v12 WHERE sourc |
| high | `src/core/graph_os/tools/graph.py:2851-2864` | LIKE '%text%' scan without indexed FTS5 fallback in lexical_search when FTS5 fails | 100K+ nodes (full table scan) | When FTS5 fails, apply a hard LIMIT immediately: LIMIT 1000. Log a warning so monitoring can detect widespread |

### src/cli/** CLI commands (cos board, cos daily, cos doctor, cos sync-all, etc.)
| Sev | Location | Issue | Breaks at | Fix |
|---|---|---|---|---|
| critical | `src/core/board_os/mcp_tools.py:1543-1549` | cos_task_reconcile loads ALL in_progress/testing/emergency tasks with NO LIMIT, then spawn | 100+ active tasks trigger 100+ c | Add LIMIT 1000 to the query, or better: batch commits_referencing calls. Spawn ProcessPoolExecutor with max_wo |
| high | `src/core/board_os/mcp_tools.py:1743` | cos_task_daily loads ALL icebox tasks into memory without LIMIT via fetchall() | 10K+ icebox tasks causes OOM ser | Add LIMIT to the icebox query: change to LIMIT 500. Icebox summary at line 1754-1759 only needs stale count +  |
| high | `src/cli/doctor.py:676` | scaffold.manifest_fresh check rglobs entire project directory to collect actual file set | 100K+ files causes full filesyst | Use find command with -prune to skip ignored dirs: subprocess.run(['find', project, '-prune', '-path', '*/.git |
| high | `src/core/board_os/mcp_tools.py:1734-1743` | cos_task_daily loads in_progress, testing, blocked, and icebox all independently without p | 5K+ tasks across all statuses ca | Add LIMIT 100 per status query. Daily standup should return top N by priority + counts, not full card list. Re |
| high | `src/core/board_os/mcp_tools.py:1612-1618` | _archive_stale_sweep loads ALL tasks matching a status without LIMIT before filtering by a | 100K tasks in icebox status caus | Push age calculation into SQL: SELECT ... FROM tasks WHERE status = ? AND (SELECT MAX(transitioned_at) FROM ta |

### RAG/Embeddings/Doc Indexer (src/core/thinking_os/embeddings.py, doc_indexer.py, search hot paths)
| Sev | Location | Issue | Breaks at | Fix |
|---|---|---|---|---|
| critical | `src/core/thinking_os/embeddings.py:456-464` | Unbounded full-table scan of embeddings without LIMIT clause — search_similar() loads ALL  | 100K+ embeddings (10M+ tasks/obs | Implement streaming cosine similarity with early termination: (1) batch-fetch embeddings in chunks (e.g. 10K r |
| high | `src/core/thinking_os/embeddings.py:127` | SentenceTransformer model download triggers network calls to HuggingFace at runtime withou | Every agent session that calls e | Enterprise fix: (1) Require HF_HUB_OFFLINE=1 environment variable before any embeddings are used; refuse to do |
| high | `src/core/thinking_os/embeddings.py:545` | reindex_all() loads entire tables into memory (fetchall) then calls upsert_embedding per r | 10K+ rows: reindex_all() calls c | (1) Use embed_texts() batch API in reindex_all: group rows into batches of 32-64, call embed_texts(batch), the |
| high | `src/core/thinking_os/embeddings.py:419-484` | search_similar() does not index the embeddings table by source_table for filtered queries  | 100K+ embeddings in a single sou | See finding #1 — streaming cosine similarity with top-K heap, or vector index (FAISS, sqlite-vec, pgvector for |

### git/commit operations at 100K-1M commits scale
| Sev | Location | Issue | Breaks at | Fix |
|---|---|---|---|---|
| critical | `/Users/ciro/Files/Project/coding-os/src/core/boa` | Unbounded git log --all --grep scan in _commits_referencing() | 100K commits: each cos_task_recl | Add --max-count=100 (or bounded parameter) to cap the scan depth. Replace unbounded 'git log --all --grep' wit |
| critical | `/Users/ciro/Files/Project/coding-os/src/core/boa` | Per-item git subprocess spawn in loop in cos_task_reclaim() | 1000+ testing zombies at 100K co | Batch task IDs into a single git log --all --grep='(TASK-001/TASK-002/...)' query and parse results into a dic |
| high | `/Users/ciro/Files/Project/coding-os/src/core/boa` | Unbounded fetchall() on tasks table in cos_task_reclaim() | 10K+ tasks in 'in_progress'/'tes | Add LIMIT clause or paginate the reclaim sweep. At minimum, cap to LIMIT 1000 per run and document that nightl |
| high | `/Users/ciro/Files/Project/coding-os/src/core/gra` | Unbounded fetchall() on graph_edges in cos_graph_cycles() | 100K+ call edges: SELECT all edg | Fetch edges in batches using LIMIT + offset pagination, or add a max_edges parameter (e.g., 100K) and raise an |
| high | `/Users/ciro/Files/Project/coding-os/src/core/boa` | Unbounded fetchall() on task_status_history in cos_task_reconcile() | 10K+ stranded tasks: loads all i | Same as #2: LIMIT 1000, paginate, or batch git operations. Reconcile should also cache commit-reference lookup |

### src/core/hooks/** per-tool-call overhead at scale (100K tasks, 100K+ commits)
| Sev | Location | Issue | Breaks at | Fix |
|---|---|---|---|---|
| high | `src/core/hooks/test-first-reminder.sh:79` | find $ROOT -maxdepth 6 on every PostToolUse Write/Edit. Walks up to 6k files on large code | 10K+ tasks with non-trivial code | Add debounce cache: pre-scan at SessionStart once (cached in $COS_AGENT_DIR/.test-locations.json), then use ca |
| high | `src/core/hooks/verify-rename-callers.sh:81` | git grep -l --word-regexp on entire repo after EVERY Edit that looks like an identifier re | At 100K+ commits + 10K files, gi | Either: (1) limit git grep to files touched in this session (use git diff scope), OR (2) add explicit timeout  |
| high | `src/core/board_os/workflow.py:152` | validate_dependencies_no_cycle() loads ALL task records into memory (SELECT task_id, depen | 10K+ tasks (function becomes O(n | Rewrite to use recursive CTE (WITH RECURSIVE) in SQL to detect cycles server-side without loading all rows. Li |

## Remediation epic (TASK-222) — child clusters
Each cluster becomes a child task; pull from this doc. Priority by severity + blast radius:
- **P0 board pagination** — replace fetch-all+cap with per-column keyset pagination (active full; complete/archive paged, cursor+total); SPA virtual-scroll. (supersedes the interim apply_budget fix TASK-220)
- **P0 embeddings at scale** — search_similar streams top-K / vector index (sqlite-vec/FAISS) instead of loading all embeddings; reindex_all batches. (offline already shipped TASK-221)
- **P0 observability/trace bounded reads** — tail-read logs/traces (256KB windows, max-N files by mtime); no full-dir glob.
- **P1 git at scale** — bound every git log/rev-list (--max-count); batch reclaim/reconcile into one grep; cache per session.
- **P1 graph centrality/ranking** — batch edge lookups (IN-clause), index uid, bounded edge scan; honest truncation signals.
- **P1 cli bounded queries** — LIMIT on daily/retro/pick; find -prune in doctor; ProcessPool cap in reconcile.
- **P1 missing indexes** — (status, completed_at) on tasks; (task_id, transitioned_at) on history; FTS5 on tasks title/goal; junction table for task_dependents (kill LIKE O(n^2)).
- **P2 hooks per-call overhead** — no full-dir/all-task/all-commit scan on every tool call; cache/debounce/indexed lookup.
- **P2 frontend** — virtual scroll on Kanban + Graph; pagination controls; SSE compression.

Full raw findings (incl. med/low + adversarial verdicts): workflow whs0yre8t output (regenerate via the enterprise-scale-audit workflow).
