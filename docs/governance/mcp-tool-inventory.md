<!-- domain:DOCS | layer:reference | ssot:true | updated:2026-05-25 -->
# MCP Tool Inventory

Purpose: Route AI agents to the correct tools for research, validation, and automation tasks.
Read when: Starting a task that requires external research, documentation lookup, package checks, or browser verification.
Skip when: The task is purely local code manipulation (use built-in tools directly) or the playbook already specifies tool routing.
Read next: The domain playbook matching your task type.

> Nav: [Docs Index](../00-index.md) | [AGENTS](../../AGENTS.md)

## Runtime Snapshot

- Verified on `2026-05-25`
- Standard runtime must match this doc before it is treated as available truth
- Agent checks available tools via its session's deferred tool list

## Coding-OS Provided

### `coding-os` MCP server

Cognitive OS — memory, graph, board, and cognition tools. SQLite backend at `.coding-os/coding-os.db`. All tools use `cos_*` prefix.

- **Health (1):** `cos_health` — DB stats, schema version, FTS5 status
- **Memory (5):** `cos_search` (5-signal ranked), `cos_timeline` (chronological), `cos_details` (full record), `cos_promote` (pattern → rule), `cos_observation_record`
- **Metrics (3):** `cos_metric_record`, `cos_metric_query`, `cos_metric_trend`
- **Learning (4):** `cos_learn_extract`, `cos_learn_suggest`, `cos_learn_validate`, `cos_learn_narrative`
- **Retrieval Quality (4):** `cos_retrieval_cite`, `cos_retrieval_learn`, `cos_retrieval_quality`, `cos_retrieval_enrichment_check`
- **Routing & Roles (6):** `cos_route_model`, `cos_route_skill`, `cos_compose_chain`, `cos_role_info`, `cos_situation_detect`, `cos_classify_prompt`
- **Docs RAG (3):** `cos_doc_search`, `cos_doc_header`, `cos_doc_headers_by`
- **Graph (22):** `cos_graph_query`, `cos_graph_resolve`, `cos_graph_context`, `cos_graph_communities`, `cos_graph_path`, `cos_graph_impact`, `cos_graph_references`, `cos_graph_rename_plan`, `cos_graph_similar`, `cos_graph_search`, `cos_graph_detect_changes`, `cos_graph_entrypoints`, `cos_graph_trace`, `cos_graph_contracts`, `cos_graph_export`, `cos_graph_centrality`, `cos_graph_ranking`, `cos_graph_dead_code`, `cos_graph_cycles`, `cos_graph_test_gap`, `cos_graph_diff`, `cos_graph_doctor` — `cos_graph_search(query)` is free-text hybrid (semantic ANN + FTS5 + centrality); `cos_graph_similar(uid)` is node-to-node.
  - `cos_graph_dead_code` = in-repo symbols with zero non-test inbound references (dead-code candidates; inverse of centrality)
  - `cos_graph_cycles` = circular dependencies as strongly-connected components (scope=imports module-level design smell | calls)
  - `cos_graph_test_gap` = prod function/method/class with zero inbound edge from a test source (untested symbols)
  - `cos_graph_diff` = graph blast-radius of a git revision range (base..head → changed files → affected symbols + downstream)
- **Board / Tasks (19):** `cos_task_board`, `cos_task_show`, `cos_task_create`, `cos_task_move`, `cos_task_ready`, `cos_task_reclaim`, `cos_task_reconcile`, `cos_task_pick`, `cos_task_claim_next` (atomic select+claim — N racing sessions each get a distinct runnable task or `claimed:null`), `cos_task_search`, `cos_task_by_filter`, `cos_task_dependencies`, `cos_task_dependents`, `cos_task_wip_check`, `cos_task_daily`, `cos_task_retro`, `cos_task_reposition`, `cos_work_log_append`, `cos_task_link` (set the optional `external_ref` forge issue/PR link — metadata, not the id)
- **Cognition (5):** `cos_supervise`, `cos_supervise_record_output`, `cos_dispatch_formula`, `cos_dispatch_formula_run`, `cos_dispatch_parallel_run`
- **Analysis (4):** `cos_analyze_task`, `cos_ambiguity_check`, `cos_backtrack_log`, `cos_discovery`
- **Logs (1):** `cos_log_query` — durable WARN+ error store query (level floor / scope glob / since / search / session / fingerprint); the agent's "what is broken now"
- **Misc (3):** `cos_traceability`, `cos_takeover`, `cos_digest_regenerate`

## Recommended External MCPs

These are commonly useful but not required. Install via Claude Code MCP settings.

- `context7` — Official framework and library documentation. Use first for framework docs.
- `ref` — URL-targeted documentation lookup and direct page reads.
- `playwright` — Browser automation and route-state verification.

## Built-in Tools

- File system → Read, Write, Edit, Glob, Grep
- Command execution → Bash (make targets, git, scripts)
- Web search → WebSearch (current facts, fallback when MCP unavailable)
- Web fetch → WebFetch (scrape single URL to markdown)
- Subagents → Agent tool (read-only research/inventory/verification only; write work runs single-agent — never use `isolation: "worktree"`)

## Task-to-Tool Selection Matrix

- Framework/library docs → context7 first, ref as fallback, WebSearch as last resort
- Memory search / past patterns → `cos_search`, `cos_timeline`, `cos_learn_suggest`
- Task board / status → `cos_task_board`, `cos_task_search`, `cos_task_by_filter`
- Single task lookup (full body) → `cos_task_show` *(in-session; never raw ls/grep/Read on docs/tasks)*
- Task create/move/complete → `cos_task_create`, `cos_task_move`, `cos_work_log_append`
- File/concept relationships → `cos_graph_context`, `cos_graph_impact`, `cos_graph_references`
- Rename planning → `cos_graph_rename_plan` (callers + impact before any rename)
- Doc search (semantic) → `cos_doc_search`; single-file frontmatter → `cos_doc_header`
- Model/skill routing → `cos_route_model`, `cos_route_skill`, `cos_compose_chain`
- Role chain for complex task → `cos_compose_chain` → writes `.coding-os/<agent>/.roles`
- Formula dispatch → `cos_dispatch_formula`, `cos_dispatch_formula_run`
- Agent performance metrics → `cos_metric_record`, `cos_metric_query`, `cos_metric_trend`
- Breakthrough narrative → `cos_learn_narrative`
- Code pattern in repo → Grep (pattern) or Glob (filename)
- Visual UI verification → playwright (if installed)
- Lints/tests/builds → Bash (make targets per playbook)

## Usage Rules

1. **Local SSOT first.** Only use external tools when local docs are insufficient or recency matters.
2. **Prefer official sources:** context7 or ref for framework docs. WebSearch for current facts.
3. **Check runtime first:** verify tool availability via session's deferred tool list before depending on any non-built-in MCP.
4. **Escalation path:** built-in tools → coding-os MCP → optional MCPs → WebSearch/WebFetch fallback.
5. **Record findings** when research changes architecture: log date, versions, and source URL in task file.
6. **Do not document aspirational tooling as available** unless runtime verification confirms it.

## Update Policy

Review this inventory when a new MCP is added or an existing one is removed. Update the `Verified on` date and the relevant section.
