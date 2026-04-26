---
id: TASK-079
title: "Graph: Wiki generation (LLM-powered per-module docs from indexed graph)"
swimlane: graph_os
kind: feature
epic: graph_os-graph-tool-parity
labels: [hub, graph, wiki, llm, P3-differentiator]
status: icebox
priority: P3
appetite: "10h"
created: 2026-04-24
started: null
completed: null
agent_session: null
depends_on: [TASK-075]
blocked_by: []
references: []
---

# TASK-079: Graph — Wiki generation (LLM-powered per-module docs)

**Outcome (one sentence):** `cos graph-wiki` generates per-module markdown with cross-refs driven by the graph (imports, members, processes), the Hub renders it under `/p/<slug>/wiki`, and generation routes through the Claude Agent SDK so outputs are cache-friendly and cheaper than equivalent graph-tool wikis.

## Read First

- [adapters/claude/sdk_dispatcher.py](../../adapters/claude/sdk_dispatcher.py) — dispatcher we route LLM calls through.
- [core/thinking_os/tools/docs.py](../../core/thinking_os/tools/docs.py) — existing doc-search MCP surface; consume similar structured output conventions.
- [core/graph_os/tools/](../../core/graph_os/tools/) — graph queries that seed each module's context.
- [docs/engineering/rules-loading.md](../../docs/engineering/rules-loading.md) — pattern for agent-agnostic routing (no hardcoded `.claude/`).
- graph-tool wiki generation (Phase P3 analysis): equivalent feature exists but without formula-dispatch integration.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** an indexed repo with ≥ 10 modules
  **When** `cos graph-wiki --module core/graph_os/` runs
  **Then** a markdown file lands at `docs/wiki/core/graph_os/README.md` with: a one-paragraph summary, a **Public API** list (exported symbols with one-liner descriptions), an **Internal** section (non-exported helpers), a **Process membership** section (from TASK-075), and a **Cross-references** section linking to wikis of imported modules.
- **Given** `cos graph-wiki --all`
  **When** run on a repo where the last wiki was 10 days ago
  **Then** only modules whose `graph.mtime` changed regenerate — others are reused from cache. A final index `docs/wiki/README.md` lists all modules with their last generation timestamp.
- **Given** the Hub UI at `http://127.0.0.1:9188/p/<slug>/wiki`
  **When** the user navigates
  **Then** a tree of modules renders on the left, the selected wiki renders in the main panel with clickable cross-references, and there is a "Regenerate this module" button that triggers incremental generation and streams progress via SSE.
- **Given** LLM generation fails (rate limit, network)
  **When** called
  **Then** the fail envelope returns `category: "transient"`, the CLI retries with backoff up to 3x, and the previous cached wiki (if any) stays served.
- **Tests:** `tests/test_graph_wiki.py` covers: cache hit path (no LLM call), cache miss path (stub SDK), partial regen, cross-ref linking integrity.

## Implementation Notes

1. **Pipeline per module:**
   a. Gather node-set from the graph (all symbols where `path.startswith(module_root)`).
   b. Build a condensed "module digest" JSON: exports, imports, top-N callers, process memberships.
   c. Render via Claude Agent SDK with a stable templated system prompt (checked in as `core/graph_os/wiki/prompts/module.md`) — prompt version is part of the cache key.
   d. Lint output against a schema (must have Summary + Public API + Internal sections) — regen once on schema fail, then give up.
2. **Cache key:** `sha256(module_digest_json + prompt_version + tool_version)`. Stored under `.coding-os/wiki-cache/<hash>.md`. Miss rate is visible in the Metrics tab (TASK-086).
3. **Cross-references:** post-pass replaces `{{link:core/graph_os/types.py}}` placeholders with relative links after all modules are generated, so ordering doesn't matter.
4. **Cost guard:** `cos graph-wiki --estimate` prints expected token spend before running; `--dry-run` produces the digest without calling the LLM.
5. **Agent-agnostic:** SDK dispatcher abstracts Claude vs future agents; do NOT import `adapters/claude/**` from `core/**` (rule P2 / P8).
6. **Hub rendering:** reuse the existing `TraceTimeline` markdown renderer style so typography is consistent; wiki page gets its own nav entry guarded by `hub-config.json::wiki.enabled`.

## Differentiator angle

graph-tool also ships a wiki, but theirs is stateless per-call. We pipe through the formula dispatch trace, so a wiki page can optionally show "this module was last touched by F9 Implementer in TASK-077" — a feature they cannot replicate without our cognition layer.

## Dependencies

- **Depends on:** TASK-075 (process membership section assumes clusters exist; without it, the section degrades to empty).
- **Unblocks:** Future "auto-answer questions about this codebase" surfaces.

## Work Log
