<!-- domain:ALL | layer:reference | ssot:true | updated:2026-04-17 -->
# Coding OS Architecture

Purpose: System-level reference for the hexagonal (ports & adapters) architecture, MCP tool catalog, database schema, and hook execution flow.
Read when: Onboarding to coding-os internals, adding a new MCP tool, or planning a schema migration.
Skip when: You only need usage docs — go to [getting-started.md](./getting-started.md). For a one-page system map with flowcharts, see [features.md](./features.md).
Read next: [features.md](./features.md) for commands + flows, [development-roadmap.md](./development-roadmap.md) for status, [phase-b-rag-plan.md](./phase-b-rag-plan.md) / [phase-c-task-store-plan.md](./phase-c-task-store-plan.md) for detailed designs.

## Overview

Coding OS is a hexagonal (ports & adapters) system that teaches AI coding agents **how to think** and **how to code**.

```
                    +------------------+
                    |   AI Agent       |
                    | (Claude/Codex/   |
                    |  Cursor/etc.)    |
                    +--------+---------+
                             |
                    +--------v---------+
                    |    ADAPTER        |  <-- Translates agent-specific format
                    | .claude/ .codex/  |
                    +--------+---------+
                             |
              +--------------v--------------+
              |          CORE               |
              |  hooks/ rules/ skills/      |
              |  thinking-os MCP server     |
              +--------------+--------------+
                             |
              +--------------v--------------+
              |        TEMPLATES            |
              |  Stack-specific rules,      |
              |  skills, playbooks          |
              +-----------------------------+
```

## Layers

### Core (agent-agnostic)

Everything in `core/` works identically regardless of which AI agent uses it.

| Component | Purpose | Key Files |
|-----------|---------|-----------|
| `thinking-os/` | MCP server — self-learning brain (memory, learning, routing, metrics) | `server.py`, `db.py`, `tools/` |
| `graph-os/` | Phase I knowledge graph (Kùzu + SQLite backends) | `backend.py`, `backends/`, `extractors/` |
| `board-os/` | Phase L Scrumban task system — the planner | `config.py`, `parser.py`, `workflow.py`, `mcp_tools.py`, `viewer/` |
| `hooks/` | Shell scripts for enforcement (45 scripts across Phases 0-L) | `thinking-os-gate.sh`, `enforce-*.sh`, `validate-task-frontmatter.sh` |
| `rules/` | Always-active workflow rules | `thinking-os.md`, `memory.md` |
| `skills/` | Deep methodology guides | `thinking-os/`, `clean-code/`, `task-driver/` |

### Adapters (per-agent)

Each adapter translates core → agent-specific config.

| Adapter | Config Format | Hook Support | Skills |
|---------|--------------|-------------|--------|
| Claude | `.claude/settings.json` | Full (PreToolUse Write/Edit) | Native `Skill` tool |
| Codex | `.codex/hooks.json` | Partial (PreToolUse/PostToolUse Bash only) | Via `AGENTS.md` + on-demand `.codex/rules/` / `.codex/skills/` |

### Templates (per-stack)

Stack-specific content: domain rules, skills, anti-patterns, verification commands.

## Key Concepts

### Complexity Gate (Cynefin)

Every task is classified before work begins:

- **CLEAR** — Known solution, just do it
- **COMPLICATED** — Known type, needs analysis (Zoom cycle)
- **COMPLEX** — Unknown, needs experimentation
- **CHAOTIC** — Emergency, act first

### Session Scoping

All state files are session-scoped via `COS_STATE_DIR`:
- `.thinking-os-gate` — current Complexity Gate classification
- `.task-current` — active task
- `.active-skill` — invoked skills
- `.zoom-checkpoint` — Plan completion marker
- `session-id` — unique session identifier

### Self-Learning Pipeline

```
Observations → Patterns → Validated Patterns → Rules
     ↑              ↑             ↑
  capture.py   learn_extract  learn_validate    promote
```

The thinking-os DB tracks everything and learns from past sessions.

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `COS_STATE_DIR` | `.coding-os` | State files directory |
| `COS_DB_PATH` | `.coding-os/thinking-os.db` | SQLite database path |
| `COS_SESSION_FILE` | `.coding-os/session-id` | Session ID file |

## MCP Tools (29 tools, `cos_*` prefix)

### Response Contract (applies to ALL tools below)

Every tool returns a JSON envelope — full spec in [engineering/mcp-error-envelope.md](engineering/mcp-error-envelope.md). Consumers (agents, tests) MUST drill through `data` / `error` rather than the top level:

```json
{ "ok": true,  "data":  <T> }
{ "ok": false, "error": { "category": "transient|validation|permission|not_found|unavailable|internal", "retryable": bool, "message": "..." } }
```

Helpers: `ok(data)` / `fail(category, message)` / `@safe_tool` decorator in [core/thinking-os/tools/_shared.py](../core/thinking-os/tools/_shared.py). `@safe_tool` converts unhandled exceptions into `fail("internal", ...)` so tracebacks never leak to the agent.

### Health (1)

- `cos_health` — DB health check (includes `rag` + `task_store` status blocks)

### Memory (4)

- `cos_search` — 5-signal ranked memory search with semantic blend when embeddings available (Phase B)
- `cos_timeline` — Recent activity timeline
- `cos_details` — Full record details
- `cos_promote` — Pattern to rule promotion

### Metrics (3)

- `cos_metric_record` — Record agent performance
- `cos_metric_query` — Query metrics with filters
- `cos_metric_trend` — Aggregated trends

### Learning (5)

- `cos_learn_extract` — Discover patterns from outcomes
- `cos_learn_suggest` — Suggest patterns for current context (accepts optional `task_description` for semantic matching)
- `cos_learn_validate` — Confirm/deny pattern usefulness
- `cos_learn_feedback` — Generate feedback drafts from rework clusters
- `cos_learn_narrative` — Record breakthrough narratives

### Routing (2)

- `cos_route_model` — Data-driven model recommendation
- `cos_route_skill` — Data-driven skill recommendation

### Graph (1)

- `cos_graph` — BFS traversal of concept/file graph

### Document RAG (1, Phase B)

- `cos_doc_search` — Semantic search over `document_chunks` populated by `make docs-index` from `docs/` (PRD, architecture, ADRs, api-contracts, page specs, engineering, ops, design). Supports `source_types` filter and per-source dedupe. Falls back gracefully when `sentence-transformers` is not installed.

### Task Store (4, Phase C)

- `cos_task_search` — Semantic + filter search over `tasks` table with LIKE fallback
- `cos_task_dependencies` — Upstream prerequisites declared by a task
- `cos_task_dependents` — Downstream tasks that depend on this one (quoted-JSON matcher prevents TASK-19 vs TASK-195 false positives)
- `cos_task_by_filter` — Structured filter by status and/or domain

## Database Schema (v6)

11 tables in SQLite with WAL mode + FTS5 (graceful degradation if FTS5 unavailable):

| Table | Migration | Purpose |
| --- | --- | --- |
| `task_outcomes` | v1 | Completed task records |
| `agent_metrics` | v1 | Per-invocation telemetry |
| `learned_patterns` | v1 | Extracted patterns with confidence |
| `experiment_log` | v1 | Hypothesis tracking |
| `observations` | v1 | Raw captured observations |
| `session_summaries` | v1 (enriched in v4) | End-of-session digests |
| `schema_version` | v1 | Applied migration log |
| `observations_fts` | v2 | FTS5 virtual table for keyword search |
| `routing_weights` | v3 | Adaptive model/skill routing |
| `outcome_history` | v4 | Outcome transition log + breakthrough narratives |
| `concept_graph` | v4 | File/concept relationships (co_edit, concept_link) |
| `embeddings` | v5 (Phase B) | Vector storage for RAG — 384-dim float32 BLOBs |
| `document_chunks` | v5 (Phase B) | Heading-aware chunks of `docs/` populated by `make docs-index` |
| `tasks` | v6 (Phase C) | Structured index of `docs/tasks/*.md` populated by `make task-sync` |

Migrations are append-only (never edit past migrations). Each new table adds a `has_<table>_table(conn)` helper following the `has_fts5_table` pattern, and gets included in `_TABLES` so `cos_health` reports its row count.

## Three-Layer Retrieval (Phase A + B + C)

The system answers different questions at three layers:

```
Layer 1: AGENT MEMORY (existing thinking-os core)
   observations, learned_patterns, outcome_history
   Question: "Have I solved this before?"
   Tools: cos_search (with semantic blend), cos_timeline, cos_details,
          cos_learn_suggest, cos_learn_narrative

Layer 2: DOCUMENT KNOWLEDGE BASE (Phase B)
   document_chunks (heading-aware chunks of docs/)
   Question: "What does the spec/rule/architecture say?"
   Tool: cos_doc_search (filter by 8 source types)
   Population: `make docs-index` reads `.coding-os/rag-config.yaml`

Layer 3: TASK REGISTRY (Phase C)
   tasks table (structured mirror of docs/tasks/*.md with dependency graph)
   Question: "Which tasks are related? What depends on what?"
   Tools: cos_task_search, cos_task_dependencies, cos_task_dependents, cos_task_by_filter
   Population: `make task-sync` (auto-runs on task-start/task-done/task-create)

Always-active (no retrieval, full-read):
   AGENTS.md, CLAUDE.md, playbooks/, core/rules/, current task detail
```

### Embeddings (`rag` optional dependency)

Phase B adds a local embedding pipeline via `sentence-transformers/all-MiniLM-L6-v2` (384 dims, ~22 MB model). Install with `uv sync --extra rag`. Without the extra, every RAG call returns empty and callers fall back to existing FTS5/LIKE behavior — zero behavior change for non-RAG users.

| Metric | Value |
| --- | --- |
| Embedding dim | 384 (float32, 1536 bytes/vector) |
| Cold query (model load) | ~10 s (first call only) |
| Warm query (1K chunks) | ~12 ms median |
| Warm query (10K chunks) | ~60 ms median |
| Warm query (50K chunks) | ~220 ms median |
| Storage | 1.5 MB per 1K vectors + metadata |

Benchmarks measured on NakoDigital's 240 task corpus + 1063 document chunks during Phase B+C end-to-end verification.

## Portability (since v0.2.0)

Projects are fully relocatable because every asset reference is indirect:

- **`.mcp.json`** points to `cos server-start` (a CLI subcommand), not an absolute path into the coding-os repo. The `cos` binary on PATH — installed via `uv tool install --editable .` — resolves the server location at runtime.
- **Symlinks** target the current coding-os install. When coding-os moves or is upgraded, `cos update` re-links everything.
- **`.coding-os/installed-manifest.json`** records every symlink the CLI manages. `cos update` uses it to detect orphans (assets that disappeared upstream) and knows exactly what to clean up without touching user-owned content.
- **`cos eject-file <path>`** converts one symlink to a copy when a user needs to customize a single upstream doc. Ejected files are never managed by `cos update`.

## Hook Execution Flow

```
Agent starts session
  → SessionStart hook → session-context.sh → reads/creates session ID,
                        injects workflow context, runs session_startup.py
                        for memory stats display

Session starts
  → SessionStart hooks (never block):
    1. warn-mcp-down.sh        — probe .mcp.json or .codex/config.toml with
                                 initialize handshake, banner loudly if MCP
                                 coding-os is unreachable
                                 (prevents the silent-death failure mode
                                 where memory/learning is off all session
                                 but the agent and human don't notice).
    2. session-context.sh      — inject workflow context + memory digest.

Agent tries to Bash a command
  → PreToolUse(Bash) hooks (ordered, fail-closed):
    1. block-secrets.sh            — no creds in args
    2. block-dangerous-commands.sh — no rm -rf, force-push, reset --hard
    3. block-uv-heredoc.sh         — CLAUDE.md rule #9: `uv run ... <<` hangs
    4. enforce-verify.sh           — block `make task-done` without verified suites

Agent tries to write code
  → PreToolUse(Write|Edit) hooks (ordered, fail-closed):
     1. block-protected-files.sh     — BLOCKS CLAUDE.md, AGENTS.md, .coding-os/,
                                       core/rules/, core/hooks/ unless the
                                       active task marker includes a governance
                                       tag (docs-update, governance, etc.).
     2. enforce-template.sh          — BLOCKS raw Write on structured docs
                                       (task/ADR/PRD/breakthrough) — redirects
                                       to the right tool.
     3. block-migration-conflict.sh  — BLOCKS duplicate MIGRATIONS versions in
                                       db.py (CLAUDE.md rule #10 — append-only).
     4. block-hardcoded-literals.sh  — BLOCKS quoted stack/adapter IDs in
                                       cli/*.py (SSOT guard, pairs with
                                       test_no_hardcoded_stacks).
     5. block-secrets.sh             — no API keys / credentials in content
     6. block-bad-patterns.sh        — no anti-patterns (bare except: pass, …)
     7. thinking-os-gate.sh          — BLOCKS unless Complexity Gate recorded
     8. enforce-task-start.sh        — BLOCKS unless task active (or CLEAR 1)
     9. enforce-doc-anchor.sh        — BLOCKS unless $COS_STATE_DIR/.doc-anchor
                                       is populated (docs-first principle —
                                       task-start.sh extracts from the task
                                       file's Source of Truth / Read First).
    10. enforce-memory-check.sh      — BLOCKS unless Memory Check recorded
                                       ($COS_STATE_DIR/.memory-check) —
                                       enforces the thinking-os Orient step.
                                       Exempt for CLEAR 1 / exploratory tasks.
    11. enforce-skill.sh             — BLOCKS unless domain skill invoked
    12. enforce-zoom.sh              — BLOCKS COMPLICATED+ without plan checkpoint

Agent finishes writing
  → PostToolUse(Write|Edit) hooks:
    1. verify-changed-file.sh    — quality check + cross-file impact analysis
    2. capture-observation.sh    — record to DB + Phase B embed observation
                                   text via embeddings.upsert_embedding().
                                   Failures now append to
                                   $COS_STATE_DIR/.capture-errors.log so
                                   check-capture-worked.sh can surface
                                   silent breakage at session end.
    3. regen-reminder.sh         — print exact `make manifest-regen` /
                                   `regen-rules` / `capture_golden` commands
                                   when source-of-truth files change. Also
                                   warns on hand-edits to generated artifacts.
    4. test-first-reminder.sh    — list the related test file or suggest
                                   a path when code changes without test.
    5. doc-sync-reminder.sh      — soft nudge: prints companion docs that
                                   describe the changed file. Project override
                                   in $COS_STATE_DIR/doc-map.yaml.

Agent runs Bash (not just code writes)
  → PostToolUse(Bash) hooks:
    1. remind-learn-validate.sh  — fires ONLY on `(make|cos) task-done`.
                                   Reads $COS_STATE_DIR/.learn-suggestions
                                   (written by Orient's cos_learn_suggest),
                                   prints a reminder to call
                                   cos_learn_validate(pattern_id, was_helpful)
                                   so learning-loop confidence actually updates.
                                   Clears the suggestions file after use.

Session ends
  → Stop hooks:
    1. check-capture-worked.sh   — session recap: count observations written
                                   with this session_id. Zero-count + code
                                   edits → warn. Surface the last 3 entries
                                   from .capture-errors.log if any. Truncate
                                   the error log for the next session.
    2. session-end.sh            — write session summary + enrichment.

Agent session ends
  → Stop hook → session-end.sh → session summary + enrichment to DB
```

### Auto-sync hooks (Phase C)

Task lifecycle scripts automatically keep the `tasks` table current — the agent never needs to call `make task-sync` manually:

- `task-start.sh` → full `sync_tasks()` in background (fire-and-forget)
- `task-done.sh` → `sync_status_only()` fast path (just flip the status column)
- `task-create.sh` → full `sync_tasks()` in background

All hooks are wrapped in `( ... ) > /dev/null 2>&1 &` so a missing DB, absent `rag` extras, or unmigrated schema never blocks the primary task lifecycle operation.
