<!-- domain:DOCS | layer:reference | ssot:true | updated:2026-01-01 -->
# MCP Tool Inventory

Purpose: Route AI agents to the correct tools for research, validation, and automation tasks.
Read when: Starting a task that requires external research, documentation lookup, package checks, or browser verification.
Skip when: The task is purely local code manipulation (use built-in tools directly) or the playbook already specifies tool routing.
Read next: The domain playbook matching your task type.

> Nav: [Docs Index](../00-index.md) | [AGENTS](../../AGENTS.md)

## Runtime Snapshot

- Verified on `2026-01-01`
- Standard runtime must match this doc before it is treated as available truth
- Agent checks available tools via its session's deferred tool list

## Coding-OS Provided

### `coding-os` (thinking-os MCP server)

Self-learning memory system. SQLite backend at `.coding-os/thinking-os.db`. 18 MCP tools in 6 categories:

- **Health (1):** `cos_health` (DB stats, schema version, FTS5 availability)
- **Memory (4):** `cos_search` (5-signal ranked search), `cos_timeline` (recent outcomes), `cos_details` (full record), `cos_promote` (pattern → rule/feedback file)
- **Metrics (3):** `cos_metric_record`, `cos_metric_query`, `cos_metric_trend`
- **Learning (5):** `cos_learn_extract`, `cos_learn_suggest`, `cos_learn_validate`, `cos_learn_feedback`, `cos_learn_narrative`
- **Routing (2):** `cos_route_model`, `cos_route_skill`
- **Graph (1):** `cos_graph` (BFS traversal of file/concept graph)

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
- Subagents → Agent tool (parallel/background task dispatch; supports `isolation: "worktree"` for filesystem-isolated parallel writes)

## Task-to-Tool Selection Matrix

- Framework/library docs → context7 first, ref as fallback, WebSearch as last resort
- Memory search / past patterns → coding-os (`cos_search`, `cos_learn_suggest`)
- Agent performance metrics → coding-os (`cos_metric_record`, `cos_metric_query`, `cos_metric_trend`)
- Model/skill routing → coding-os (`cos_route_model`, `cos_route_skill`)
- File/concept relationships → coding-os (`cos_graph`)
- Breakthrough narrative capture → coding-os (`cos_learn_narrative`)
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
