<!-- domain:ROADMAP | layer:plan | ssot:true | updated:2026-04-24 -->
<!-- domain:graph_os | layer:roadmap | ssot:true | updated:2026-04-21 -->
# graph_os Redesign — MVP → v1 → v2 Checklist

> P: SSOT slice list for the graph_os + unified WebUI redesign — every slice maps to one Scrumban task.
> R: Picking the next slice to build, or sizing scope when proposing a graph_os change.
> S: Querying the deployed graph — see [docs/engineering/graph_os-queries.md](../engineering/graph_os-queries.md).
> N: [docs/phase-i-knowledge-graph-plan.md](../phase-i-knowledge-graph-plan.md), [docs/benchmarks/graph_os.md](../benchmarks/graph_os.md)

> Master checklist for the graph_os + unified WebUI redesign. SSOT for slice scope + completion criteria. One Scrumban task per slice.

## Context (one paragraph)

graph_os today ships 11 MCP tools + a one-shot HTML export viewer. Goal: raise it to a external graph tooling-class system — agent-facing MCP surface stays, human-facing side becomes a unified React SPA on **port 9188** covering graph + scrumban board + cognition traces + future systems. Anti-hairball via depth-bounded BFS + node-type filters + CONTAINS spine (Folder→File→Class→Method). See also: [core/graph_os/](../../core/graph_os/), [core/board_os/](../../core/board_os/).

**Port:** 9188 (IANA-unassigned; 4747–4748 were reserved by other conventions).

**Stack:** React 18 + Vite + TypeScript + Tailwind v4 + Sigma.js v3 + Graphology + ForceAtlas2 (npm latest as of 2026-04-21).

---

## MVP

### S1 — Correctness bundle (Opus)

- [ ] B1 concurrency: SQLite `check_same_thread=False` + WAL PRAGMA + full write-lock covering reads on Kuzu
- [ ] B2 `_walk_bfs` edge duplication: append only when `next_uid not in visited_uids`
- [ ] B3 `cos_graph_trace` edge filter: add `handles_route|handles_tool|handles_event|dispatches|awaits`
- [ ] B4 `cos_graph_path`: raise `limit` to 1000, document truncation, add `truncated: bool` in meta
- [ ] B5 Kuzu `delete_node`: MATCH count first, then DETACH DELETE
- [ ] B6 N+1: add `get_nodes_bulk(uids)` to Protocol + both backends
- [ ] B7 singleton resource leak: close old before replace
- [ ] B11 `GraphNode.metadata`: use `types.MappingProxyType` + frozen tuple of items, OR drop frozen
- [ ] B17 CHECK constraint: migration v13 adds `CHECK (confidence BETWEEN 0 AND 1)` on edges
- [ ] Test: `core/graph_os/tests/test_concurrency.py` — ≥4 threads mixed R/W
- [ ] `make verify` green
- [ ] Files: `types.py`, `backend.py`, `tools/graph.py`, `backends/sqlite_backend.py`, `backends/kuzu_backend.py`, migration in `thinking_os/db.py` (v13)

### S2 — API semantics cleanup (Sonnet)

- [ ] B12 `downstream/upstream` docstring clarity + deprecation path for ambiguous names
- [ ] B13 `cos_graph_similar`: add `sample_nodes(kind, n)` to Protocol, use it instead of edge-endpoint bias
- [ ] B14 `cos_graph_contracts`: add contract test asserting extractor edge_types match tool string list
- [ ] B15 `cos_graph_detect_changes`: deep walk feeds `downstream_tasks`, not just 1-hop
- [ ] B20 `_graph_unavailable` return type: JSON-encode the fail envelope
- [ ] B21 `cos_graph_context include_content=True`: inline source from `file_path` + `start_line..end_line`
- [ ] B22 cap `meta.query` to 500 chars
- [ ] B24 CLI wrapper `cos graph detect-changes --staged` that runs `git diff --name-only` and forwards
- [ ] Files: `tools/graph.py`, `backend.py` (protocol), both backends, `cli/graph.py`

### S3 — CONTAINS spine + node-kind enum (Opus, schema migration)

- [ ] Define `NodeKind` StrEnum in `types.py`: `folder, file, class, method, function, variable, import_, route, tool, event, task, doc_file, doc_heading, rule, skill, contract, community` (≥17 values)
- [ ] Extractors emit `contains` edges: Folder→File, File→Class/Function, Class→Method
- [ ] Migration v13 (append-only, Rule 9): no schema change, but reindex required — flag in meta
- [ ] Extractors to update: `code_python`, `code_ts`, `code_shell`, `code_yaml`, `md_links`, `task_deps`
- [ ] Back-compat: accept old free-string kinds during read, normalize on write
- [ ] Test: `test_contains_spine.py` asserts tree integrity on sample repo
- [ ] `cos graph-reindex` after this lands
- [ ] Files: `types.py`, all seven extractors, one new test

### S4 — Unified web server backbone (Sonnet)

- [ ] New package `core/web/` with `server.py`, `routes/`, `__init__.py`
- [ ] FastAPI + uvicorn (pinned latest as of 2026-04-21)
- [ ] Port 9188 (env `COS_WEB_PORT`)
- [ ] Routes:
  - `/api/graph/*` — wrap 11 `cos_graph_*` (thin adapter returning envelope JSON)
  - `/api/board/*` — wrap `cos_task_*`
  - `/api/cognition/*` — wrap `cos_cognition_*` + trace reader
  - `/api/search/*` — wrap `cos_search` + `cos_doc_search`
  - `/api/stream/events` — SSE for live board updates
  - `/health` + `/metrics` (Prometheus format via `graph_os.enterprise.metrics()`)
- [ ] CORS: `http://localhost:5173` (Vite dev) + same-origin in prod
- [ ] Static serve `core/web/ui/dist/` when built
- [ ] CLI: `cos web [--port 9188]` launches uvicorn
- [ ] Test: `test_web_server.py` spin-up + each route returns 200
- [ ] Kill RateLimiter dead code — wire it here per-route OR delete
- [ ] Kill backend probe stale-write — health endpoint tests live backend
- [ ] Files: `core/web/**`, `cli/web.py`

### S5 — React SPA scaffold (Sonnet for scaffold, Opus for graph viz)

- [ ] `core/web/ui/` — Vite project, React 18, TypeScript, Tailwind v4
- [ ] Router (react-router-dom v6): `/graph`, `/board`, `/cognition`, `/search`
- [ ] Layout: header (logo, search, AI-panel toggle) + left nav + main + right inspector
- [ ] Graph page:
  - Sigma.js v3 + Graphology + ForceAtlas2
  - **empty canvas until a root is picked** (anti-hairball #1)
  - depth slider (1/2/3/All)
  - node-type filter panel (checkbox per `NodeKind`)
  - edge-type filter panel
  - color legend (per-kind)
  - node inspector panel (uid, kind, file:line, signature, doc_blob, evidence)
  - left tree: CONTAINS tree view (Folder→File→Class)
- [ ] Board page: Kanban columns, SSE-live updates
- [ ] Cognition page: trace timeline (from `cognition-trace-replay.html` logic)
- [ ] Search page: unified search over memory + docs + graph
- [ ] API client: typed `fetch` wrapper with envelope unwrapping
- [ ] Build: `npm run build` → `dist/` served by FastAPI
- [ ] Dev: `npm run dev` on 5173, proxies `/api` to 9188
- [ ] Deprecate: `core/board_os/viewer/` marked deprecated, redirect to `/board`
- [ ] Deprecate: `core/graph_os/viewer/` static HTML kept for `cos graph-viz` CLI compat, but SPA is primary

### S6 — Cleanup + integration polish (Opus)

- [ ] Orchestrator (`core/graph_os/orchestrator/`): decide — wire into reindex_dispatch for parallel extraction, OR remove entirely. Recommendation: **remove for now, reintroduce when actually needed**.
- [ ] RateLimiter: wire into `core/web/server.py` per-route middleware
- [ ] Metrics: wire into every MCP tool + web route
- [ ] Update `AGENTS.md` / `CLAUDE.md` entries pointing at web UI
- [ ] Update `graph-explorer` skill to mention `/graph` URL
- [ ] Adapter regen: `make regen-adapter-templates` if any hook registry changed
- [ ] Docs: `docs/engineering/web-ui.md` NEW (since docs are stale, write this fresh)
- [ ] Remove `core/board_os/viewer/` after confirming parity

---

## v1 (post-MVP)

### V1 — File-level incremental indexing (Opus)

- [ ] Per-file `content_hash` cache in SQLite table `file_index_state`
- [ ] `reindex_dispatch.dispatch` checks hash, skips unchanged
- [ ] `cos graph-reindex --force` flag bypasses cache
- [ ] Test: touch file, reindex, assert skipped; modify, reindex, assert processed

### V2 — Leiden communities precomputed (Sonnet + Opus)

- [ ] Add `graphology-communities-leiden` (npm) OR Python-side `leidenalg`
- [ ] `community` node kind + `member_of_community` edge
- [ ] Run at end of ingest pipeline
- [ ] UI: cluster view panel — click cluster → auto-depth 2 BFS from cluster centroid

### V3 — AI chat panel (Opus)

- [ ] Library: `langgraph` + `langchain` (Python side) OR `@langchain/langgraph` (JS)
- [ ] Decision: server-side chat (keeps keys secret) vs client-side (external graph tooling way). Prefer **server-side** — we already run the backend.
- [ ] Multi-provider: Anthropic (default), OpenAI, Gemini, Ollama via env
- [ ] Tools exposed to ReAct: same 11 `cos_graph_*` + `cos_search` + `cos_doc_search`
- [ ] UI panel: chat pane, right-side, togglable
- [ ] Streaming via SSE

---

## v2 (future)

### V4 — Multi-repo registry + LRU pool
- [ ] `~/.coding-os/registry.json`
- [ ] LRU pool (5 repos, 8 conn/repo, 5min idle) — copy external graph tooling `pool-adapter.ts` pattern
- [ ] MCP `list_repos` tool + `repo` param on every graph tool

### V5 — BGE-M3 embeddings (already Phase I.1 in roadmap)
- [ ] Per-node embedding column
- [ ] Hybrid BM25 + vector with RRF K=60
- [ ] Process-grouped results

### V6 — In-browser WASM mode
- [ ] `transformers.js` for embeddings
- [ ] WASM SQLite or WASM Kuzu build
- [ ] Runtime switch: detect `localhost:9188`, fall back to WASM

### V7 — Docker compose
- [ ] `Dockerfile.server` + `Dockerfile.web`
- [ ] `docker-compose.yaml`
- [ ] GHCR publish

---

## Execution rules

1. One slice = one Scrumban task + one branch + one PR-worthy commit bundle.
2. `make verify` must stay green between slices.
3. No slice touches files outside its declared set.
4. v1 only starts after MVP fully ticked.
5. Docs updates are per-slice, inline — no separate doc slice.

## Progress log

- 2026-04-21 — checklist created. Awaiting S1 dispatch.
