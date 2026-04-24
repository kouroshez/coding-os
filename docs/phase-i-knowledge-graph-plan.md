<!-- domain:ALL | layer:reference | ssot:true | updated:2026-04-19 -->
# Phase I — `graph-os` (Industrial Knowledge Graph Subsystem)

> **Rename note:** The pre-rewrite plan called this phase "knowledge-graph". The subsystem itself is now a first-class module — **`graph-os`** — sibling to `thinking-os`. Same file retained for backward compatibility with old references.

Purpose: Build a production-grade, multi-language, multi-repo code & documentation knowledge graph that (a) the agent queries before every non-trivial edit to understand blast radius, (b) the human inspects visually via a first-party viewer, and (c) scales to monorepos with 500k+ symbols without degrading agent latency. `graph-os` is the second cognitive pillar of `coding-os`, alongside `thinking-os` (cognition/memory) and the hook regime (enforcement).

Read when: Starting any `I.*` slice, auditing the extraction pipeline, adding a new language, wiring a new MCP tool, or changing the symbol-resolution semantics.

Read next: [core/thinking_os/graph.py](../core/thinking_os/graph.py), `concept_graph` schema in [core/thinking_os/db.py](../core/thinking_os/db.py) migration v4, [docs/phase-h-auto-sync-plan.md](./phase-h-auto-sync-plan.md), [docs/code-os-core-docs/thinkingos-formulas/formulas-en.md](./code-os-core-docs/thinkingos-formulas/formulas-en.md) (roles).

---

## 1. Why — The Problem graph-os Solves

`coding-os` already answers two of the three "retrieval" questions: *"have I solved this before?"* (memory) and *"what does the spec say?"* (docs RAG). It does **not** answer the third — the one professional engineers ask most often:

> *"If I change this function, what breaks? What should I review? What else uses it? What docs describe it? What task wrote it?"*

An agent without this answer is blind. It edits a file, ships, and causes cascading failures because it could not see the web of dependencies around the code. Grep finds the string; it does not know `user.address.getCity()` resolves to `City.getName()` via a type-binding chain across 4 files.

`graph-os` closes this gap. One subsystem, one SQLite table family, one MCP surface, one viewer — the agent and the human share a single graph of *everything that can reference anything else*:

- **Docs graph** — `[link](./path.md)` + `[[wikilink]]` + frontmatter `ssot_of:` references.
- **Code graph** — imports, calls, class-inherits, method-overrides, property-accesses, route-handlers, MCP-tool-handlers, decorators.
- **Task graph** — `tasks.dependencies` (already parsed by Phase C) + task→doc + task→commit edges.
- **Cross-layer edges** — task→doc→code trails that let an agent answer *"which task produced this function, which doc spec'd it, which commit introduced it, what changed since?"*

This is what Sourcegraph Cody, Continue, Cursor, GitHub Copilot Workspace, and graph-tool all attempt. `graph-os` leapfrogs them by being **native to the agent's cognitive loop** — not a plugin bolted on, but a first-class retrieval layer queried in the same MCP envelope as `cos_search` and `cos_doc_search`.

---

## 2. Nature — `graph-os` as a Module

```
core/
├── thinking-os/     ← cognition + memory   (DB v1-v11)
├── graph-os/        ← NEW: knowledge graph (DB v12+)
└── hooks/           ← enforcement layer
```

**What graph-os IS:**

- A parallel subsystem to `thinking-os`, with its own code tree, its own tests, its own MCP tools, its own schema migration, its own viewer.
- A tenant of the **same** SQLite file (append-only migrations, Rule 10). Uses the existing FTS5 + embedding infrastructure.
- Wired into the **same** MCP server (`core/thinking_os/server.py`). Tools follow the `cos_graph_*` prefix so they show up alongside the other 21 tools.
- Wired into the **same** auto-reindex hook (`auto-reindex-docs.sh`, Phase H) so every Write/Edit triggers incremental graph updates.

**What graph-os is NOT:**

- Not a separate service — no HTTP server, no separate daemon. The viewer is a static HTML file; the graph lives in the same SQLite.
- Not a replacement for `cos_doc_search` or `cos_search` — it's the **third retrieval layer** (semantic docs → past patterns → structural graph).
- Not a generic tool like graph-tool. `graph-os` is *custom-shaped for coding-os*: it knows about tasks, docs, skills, hooks, MCP tools. Edges surface those first-class concepts.

**Biological analogy (extending the `core/`-DNA metaphor):**

| `thinking-os` | `graph-os` |
|---|---|
| Hippocampus — episodic memory of past observations | Corpus callosum — the wiring between all brain regions |
| "Have I seen this?" | "What is this connected to?" |

---

## 3. Core Principles

- **P-I-1. Native custom fit.** Every node kind, edge kind, and MCP tool is designed for `coding-os`. Generic tools (graph-tool, Obsidian) inform the schema but do not constrain it.
- **P-I-2. Tree-sitter + LSP always on.** Tree-sitter gives us 15+ languages, zero-config, AST-grade accuracy. For TypeScript generics + Python complex types where AST alone misses ~15% of edges, LSP adapters (pyright, tsserver) run by default — not opt-in — because this is an enterprise product aimed at >95% precision. LSP subprocess managed with 5s timeout + circuit breaker; degrades gracefully if LSP crashes.
- **P-I-3. Two-pass extraction.** Per-file scope extraction → cross-file symbol resolution. Copied from graph-tool's proven design (`graph-tool-shared/src/scope-resolution/`). Single-pass regex is not negotiable for accuracy.
- **P-I-4. Evidence-weighted edges.** Every edge carries `confidence ∈ [0,1]` and `evidence[]` (the signals that composed it). No binary "matched/not-matched". Agents use the confidence to decide whether to trust or verify.
- **P-I-5. Incremental by default.** Content-hash per file; AST-hash per symbol. Re-parse only changed files. Cascade invalidation when a file's exports change.
- **P-I-6. Token-aware tool surface.** Every MCP tool has `limit`, `max_depth`, `max_nodes`, `include_content` defaults tuned to keep responses under 4k tokens. No "dump the whole graph" anti-pattern.
- **P-I-7. Graph-native storage by default.** Kùzu (embedded columnar graph DB, Cypher-capable, Apache 2.0) is the **primary** backend for graph_nodes + graph_edges + graph_node_embeddings. SQLite stays for memory / docs / tasks (its relational strength). Two specialized stores — each for what it does best. SQLite backend kept as a fallback for constrained environments (no Kùzu binary available).
- **P-I-8. Multi-agent orchestrator, fully implemented.** Indexing workers are `thinking-os` agent roles coordinated by a real orchestrator — parallel dispatch, progress metrics, cancellation, health reporting. Not a stub, not `multiprocessing`.
- **P-I-9. Graph-of-docs + graph-of-code + graph-of-tasks, unified.** One schema, many extractors. The agent asks "what breaks if I change this doc?" the same way it asks about code.
- **P-I-10. Dogfood at scale.** The `coding-os` repo itself is the first stress test. 31 hooks, 21 MCP tools, 1083 tests (baseline 2026-04-19), 3 templates × 2 adapters = ~1500 edges on day one.
- **P-I-11. Determinism & pinned parsers.** Indexing must be reproducible — same inputs → byte-identical `uid`s → same edges. Tree-sitter core + per-language grammars + Kùzu + BGE-M3 tokenizer are **pinned** in `pyproject.toml::optional-dependencies.graph-os`. Golden test in I.0 re-indexes a fixture 3× and asserts byte-identical node/edge rows. Grammar upgrades are their own slice (Phase J).
- **P-I-12. Observability budget — every new tool carries its cost.** Each `cos_graph_*` tool declares, at registration time, (a) default token budget, (b) hard cap, (c) expected P95 latency per backend (Kùzu vs SQLite), (d) storage cost per invocation. `cos_health` surfaces the budget vs actual; `cos doctor` check C18 fails when a tool exceeds its declared latency envelope on three consecutive runs. No silent cost creep.

---

## 4. Competitive Landscape — What We Copy, What We Improve

graph-tool study — source: https://github.com/githubnext/graph-tool (Apache 2.0). Copy-reference snippets that `graph-os` adapts (scope-resolution, 7-step registry lookup, evidence composition, call-form classification) live under `docs/references/graph-tool-notes.md` — pinned to a specific commit. Do **not** rely on `/tmp` paths; they are local to the authoring machine and disappear on checkout.

| System | Parser | Graph store | Scale | Multi-lang | Agent-native | Custom-domain | Killer gap |
|---|---|---|---|---|---|---|---|
| **Sourcegraph Cody** | tree-sitter + SCIP indexers | custom (Zoekt) | trillion | 40+ | No (API plugin) | No | closed; cannot extend taxonomy |
| **graph-tool** | tree-sitter + custom scope | Kùzu (in-mem → disk) | 500k symbols | 15+ | Yes (MCP) | No (generic) | no task/doc layer; standalone |
| **Obsidian + Dataview** | regex | JSON | 50k notes | No (MD only) | No | No | code-blind |
| **Continue Dev (graph mode)** | LSP | in-memory | small repos | LSP-dependent | Yes | No | runtime LSP dependency |
| **GitHub Copilot Workspace** | proprietary | proprietary | large | unknown | closed | No | not inspectable |
| **Cursor** | proprietary (symbol graph) | proprietary | large | many | closed | No | not inspectable |
| **graph-os** | tree-sitter + LSP-opt + regex-fallback | SQLite (+ Kùzu adapter) | 500k → 5M | 15+ | Yes (native) | **Yes (tasks/docs/skills/hooks)** | — |

**Concrete copies from graph-tool:**

1. **Scope extractor** (5-pass tree-sitter AST walker) — reference: `graph-tool-shared/src/scope-resolution/scope-extractor.ts` (graph-tool upstream). Adapted to Python under [core/graph-os/extractors/](../core/graph-os/extractors/) in I.4.
2. **Symbol table + 7-step registry lookup** — reference: `graph-tool/src/core/ingestion/model/symbol-table.ts`. The 7 steps (same-scope → enclosing-scope → explicit-import → wildcard-import → global-name → arity-narrowed → fuzzy) become our resolution DAG.
3. **Evidence composition** — reference: `graph-tool-shared/src/scope-resolution/registries/evidence.ts`. The `confidence = sum(signal_weights) clamped at 1.0` pattern with per-signal trace — normalized into our `graph_evidence_v12` table (§5.3).
4. **Call-form classification** — distinguishing `new Foo()` vs `Foo.bar()` vs `bar()` at AST level. Tree-sitter queries per call-form.
5. **MCP tool signatures** — `query`, `context`, `impact`, `detect_changes` as our `cos_graph_*` surface.

**What we add on top of graph-tool:**

- **Task edges** (`docs/tasks/TASK-199.md → docs/tasks/TASK-195.md`) — graph-tool is code-only.
- **Doc edges** (`[link](./other.md)` + frontmatter `ssot_of:` + heading-scoped citations) — graph-tool is code-only.
- **Cross-layer edges** (task → doc → code → commit) — the one-stop dependency trail.
- **Agent-role-aware extractors** (see §13) — indexers run as `thinking-os` roles, not detached workers.
- **Confidence-aware MCP envelope** (Rule 14, `fail("internal",...)` on extractor panics) — graph-tool tools are less defensive.

**What we explicitly DO NOT copy:**

- LadybugDB / Kùzu as default (SQLite first, adapter later).
- Web UI / Express server / CLI-as-app shell (we have `cli/main.py` already).
- Worker pool orchestration (we have `thinking-os` agent roles).
- Community detection (Leiden clustering) — deferred to Phase J.
- Process tracing (entry-point → terminal walk) — deferred to Phase J.

---

## 5. Node & Edge Taxonomy

The taxonomy is a *superset* of graph-tool's (code-focused) plus `coding-os` first-class concepts (task/doc/skill/hook/tool).

### 5.1 Node kinds (label enum)

**Code:**
- `code:file` — source file (python/ts/tsx/sh/go)
- `code:module` — Python `__init__.py` / TS barrel / Go package
- `code:class`, `code:interface`, `code:enum`, `code:type_alias`, `code:decorator`, `code:namespace`
- `code:function`, `code:method`, `code:constructor`, `code:lambda` (named only)
- `code:variable`, `code:constant`, `code:property`, `code:field`
- `code:parameter`, `code:import` (import statement itself as a node, links raw → resolved)

**Doc:**
- `doc:file` — markdown file
- `doc:heading` (h1–h6 with stable slug anchors)
- `doc:code_block` (fenced code blocks; optional Phase J)
- `doc:frontmatter_key` (e.g., `ssot:true`, `domain:backend`)

**Task:**
- `task:file` — `docs/tasks/TASK-NNN-*.md`
- `task:phase` (optional, when phase is parseable)

**Coding-OS first-class:**
- `cos:skill` — `core/skills/<name>/SKILL.md`
- `cos:hook` — `core/hooks/<name>.sh`
- `cos:rule` — `core/rules/<name>.md`
- `cos:mcp_tool` — `cos_*` tool name
- `cos:command` — `core/commands/<name>.md`
- `cos:scaffold` — `templates/**/scaffold/**` files
- `cos:route` — HTTP route handler (for consumer projects; generic)

**Meta:**
- `meta:commit` — `sha:<hash>` (optional, for git-diff integration in Phase J)
- `meta:agent_run` — `run:<session_id>:<turn>` (Phase J, observability)

### 5.2 Edge kinds (relation enum)

**Containment:**
- `contains` — file→class→method; doc→heading→subheading

**Code semantics:**
- `imports`, `re_exports`, `exports`
- `calls`, `constructs` (`new Foo()`), `accesses_field`, `accesses_property`
- `inherits_from`, `implements`, `overrides`, `extends`, `mixes_in`
- `defines_type`, `uses_type`, `annotates_with`
- `decorates`, `is_decorated_by`
- `handles_route`, `handles_tool` (declarative handler)
- `queries_orm` (ORM model reference; Phase J)

**Docs:**
- `links_to` — inline `[text](path)` + `[[wiki]]`
- `ssot_of`, `read_next`, `read_before` (from our frontmatter convention)
- `cites_heading` — `[text](path#anchor)` → the specific heading node

**Tasks:**
- `depends_on` — from `tasks.dependencies` JSON
- `blocks` — inverse of depends_on (materialized for fast dependents queries)
- `references_doc` — task file → doc file (from "Source of Truth" / "Read First" sections)
- `produces_code` — task file → file it modified (derived from git log + task marker)

**Cross-layer:**
- `spec_of` — doc → code (when a code file's `<!-- ssot: docs/X -->` points back)
- `implements_spec` — inverse of spec_of
- `tested_by` — code → test file (by convention `test_<name>.py`)

### 5.3 Edge row shape — evidence normalized for scale

Evidence is **normalized into its own table** so the hot edge row stays lean and indexable. At 500k-file scale, inline `evidence_json TEXT` balloons to ~3GB unindexed; the 1:N `graph_evidence_v12` table below indexes on `edge_id` and is fetched on-demand by MCP tools (default `include_evidence=False`).

```sql
-- Hot table: lean edge row
CREATE TABLE graph_edges_v12 (
  id            INTEGER PRIMARY KEY,
  source_id     INTEGER NOT NULL REFERENCES graph_nodes(id),
  target_id     INTEGER NOT NULL REFERENCES graph_nodes(id),
  edge_type     TEXT    NOT NULL,              -- enum from §5.2
  confidence    REAL    NOT NULL DEFAULT 1.0,  -- [0,1]
  extractor     TEXT    NOT NULL,              -- which extractor wrote this
  source_span   TEXT,                          -- "file.py:42-58" for citation
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL,
  UNIQUE(source_id, target_id, edge_type, extractor)
);
CREATE INDEX idx_ge_source ON graph_edges_v12(source_id, edge_type);
CREATE INDEX idx_ge_target ON graph_edges_v12(target_id, edge_type);
CREATE INDEX idx_ge_type   ON graph_edges_v12(edge_type);

-- Normalized evidence: one row per signal that contributed to an edge
CREATE TABLE graph_evidence_v12 (
  id             INTEGER PRIMARY KEY,
  edge_id        INTEGER NOT NULL REFERENCES graph_edges_v12(id) ON DELETE CASCADE,
  signal_name    TEXT    NOT NULL,             -- e.g. "same_scope", "type_binding", "lsp_overlay"
  weight         REAL    NOT NULL,             -- contribution to the edge's confidence
  note           TEXT,                         -- human-readable detail for audits
  created_at     INTEGER NOT NULL
);
CREATE INDEX idx_gev_edge ON graph_evidence_v12(edge_id);
```

**Fetch contract** — MCP tools fetch evidence **on demand**:
- `cos_graph_context(uid, include_evidence=False)` → default; returns edges only, no evidence JOIN, ~1k-token payload.
- `cos_graph_context(uid, include_evidence=True)` → JOINs `graph_evidence_v12`; returns `{signals: [...]}` per edge; warns in envelope when JOIN produces >1000 signals (`meta.evidence_truncated=true`).

**Storage audit (I.8 ship gate):** at 10k-file dogfood, DB size ≤ 200MB (hot + evidence). At 100k-file fixture (I.13), DB size ≤ 2GB.

### 5.4 Node row shape

```sql
CREATE TABLE graph_nodes (
  id           INTEGER PRIMARY KEY,
  kind         TEXT NOT NULL,       -- e.g. 'code:method'
  label        TEXT NOT NULL,       -- human-readable
  uid          TEXT NOT NULL UNIQUE,-- stable identity: "code:method:app/user.py::User.get_name"
  file_path    TEXT,                -- source file (NULL for virtual nodes)
  start_line   INTEGER,
  end_line     INTEGER,
  signature    TEXT,                -- function sig / class decl
  lang         TEXT,                -- py/ts/tsx/sh/md/yaml
  doc_blob     TEXT,                -- docstring / frontmatter, searchable
  ast_hash     TEXT,                -- for incremental re-resolution
  content_hash TEXT,                -- for file-level invalidation
  metadata_json TEXT DEFAULT '{}',
  created_at   INTEGER NOT NULL,
  updated_at   INTEGER NOT NULL
);
CREATE INDEX idx_gn_kind_lang ON graph_nodes(kind, lang);
CREATE INDEX idx_gn_file      ON graph_nodes(file_path);
CREATE VIRTUAL TABLE graph_nodes_fts USING fts5(label, signature, doc_blob, content=graph_nodes);
```

`concept_graph` (migration v4, `co_edit` edges only) stays untouched — legacy. New code writes to `graph_edges_v12`. An optional one-time migrator backfills `concept_graph` rows as `co_edit` edges into v12 for query uniformity. (Schema reality check: the live DB is at v11 — v12 is the next append-only slot. `block-migration-conflict.sh` enforces no duplicate version numbers.)

---

## 6. Extraction Pipeline — Six Stages

```
Discovery → Parse → Scope Extract → Symbol Table → Resolve → Embed
   (1)      (2)        (3)             (4)         (5)      (6)
```

### Stage 1 — Discovery

- Walk the repo respecting `.gitignore` + `.coding-os/rag-config.yaml::graph.include/exclude`.
- Classify each path: `code:py | code:ts | code:tsx | code:sh | doc:md | task:md | cos:*`.
- Produce `FileTask[]` with content hashes. If `content_hash` matches last run → skip to Stage 6.

### Stage 2 — Parse

- Dispatch per-language tree-sitter grammar. One `tree-sitter` per process (shared memory), one AST per file.
- For markdown: use the existing `doc_indexer.py` chunker, extended to also emit links + headings.
- Output: `ParsedFile { ast, lang, imports_raw, references_raw }`.

### Stage 3 — Scope Extract (per-file, graph-tool-adapted)

Five-pass AST walk to build a `ScopeTree` per file:

1. **Declarations** — each `def`/`class`/`const` → `SymbolDefinition { name, kind, scope_id, span }`.
2. **Imports** — `from X import Y` → `ImportDecl { module, local_name, kind }`.
3. **References** — every identifier use → `ReferenceSite { name, call_form, scope_id, span }` (unresolved).
4. **Type annotations** — `x: User` → `TypeBinding { var, type_name, scope_id }`.
5. **Decorators** — `@foo` → `DecoratorRef`.

Output: `ParsedFile` row persisted to a scratch table, one per source file.

### Stage 4 — Symbol Table build (cross-file, in-memory)

- Aggregate all `SymbolDefinition` across files into an in-memory `SymbolTable` keyed by `(module, name, arity)`.
- Resolve raw imports: `from ./utils import foo` → `SymbolDefinition` row in `utils.py`. Handle:
  - Relative imports (respecting `__init__.py` packages).
  - TS path aliases (read `tsconfig.json::paths` + Vite aliases).
  - Python `sys.path` + `setup.py` / `pyproject.toml::[tool.uv]`.
  - Go module paths (`go.mod`).
- Persist `imports` edges now (they're already resolved).

### Stage 5 — Resolve References

For each `ReferenceSite`, run the **7-step registry lookup** (graph-tool's core insight):

1. **Same-scope lookup** — is the name defined in the current scope? (weight 0.5)
2. **Enclosing-scope walk** — walk `ScopeTree` upward. (weight 0.3 per level up)
3. **Explicit import** — is the name in an `ImportDecl`? (weight 0.4)
4. **Wildcard import** — is it in a `from X import *`? (weight 0.2, lower confidence)
5. **Type-binding chain** — for `x.y.z()`, walk `TypeBinding` + field/property chain. (weight 0.3 per hop)
6. **Global name** — is it in any module's top-level? (weight 0.1)
7. **Arity-narrowed / fuzzy** — if multiple candidates survive, narrow by arity + name-similarity. (weight 0.1)

`confidence = sum(applicable weights), clamped to [0, 1]`. For every applicable signal, one row is written to `graph_evidence_v12` (normalized — see §5.3) linked to the edge via `edge_id`. No inline `evidence_json` TEXT column.

Output: `calls`, `accesses_field`, `constructs`, `overrides`, `inherits_from` edges.

### Stage 6 — Embed (BGE-M3)

- **Model upgrade:** retire MiniLM-L6-v2 (English-only, 384-dim, ~80MB) → adopt **BGE-M3** (multilingual incl. Persian/English, 1024-dim, ~560MB, Apache 2.0). Rationale:
  - Persian docs (like `formulas-v2.md`) index correctly — MiniLM treats them as low-signal noise.
  - BGE-M3 does hybrid retrieval: dense + sparse + multi-vector from one pass. Three retrieval signals, one model.
  - Handles both natural-language docs AND code symbols well (ranked top-5 on both MTEB and CoIR benchmarks).
  - Backward-compat: existing embeddings re-computed in the background (non-blocking — see §6 Stage 6 "Background migration contract"); stored in v12 `graph_node_embeddings` (1024-dim BLOB, Kùzu-native vector column) + doc_chunks re-embedded to match. During the re-embed window, both dim=384 and dim=1024 vectors coexist; queries route by `embedding_dim` column on the `embeddings` table (v12 adds this column to avoid the [embeddings.py:46](../core/thinking_os/embeddings.py#L46) `cosine_similarity` silent-empty bug when dims mismatch).
- For each public code symbol (function, class, route, tool): embed `signature + docstring + enclosing_class_name`.
- Persist to `graph_node_embeddings` stored in Kùzu alongside nodes (Kùzu supports vector properties natively via HNSW).
- Reuse cache: if `ast_hash` unchanged → skip embedding.

#### Background migration contract (MUST — non-blocking)

`scripts/migrate_embeddings_minilm_to_bge_m3.py` runs as a dedicated `thinking-os` role **outside** the MCP server's startup path — no blocking boot:

- Migration v12b adds `embedding_dim INTEGER DEFAULT 384` to the existing `embeddings` table, then schedules the migrator role via the orchestrator (§13).
- The migrator role (`migrator:embeddings`) chews through rows in batches of 256, each batch in its own transaction (crash/SIGTERM loses ≤256 rows of work).
- Progress checkpoint persists to `.coding-os/.embedding-migration.json` (`{total, done, eta_seconds, last_source_table}`) for <1s resume.
- While migration is in progress, [core/thinking_os/embeddings.py](../core/thinking_os/embeddings.py) `cosine_similarity()` **must route by `embedding_dim`** — it MUST NOT silently return `[]` on dim mismatch (the current [embeddings.py:46](../core/thinking_os/embeddings.py#L46) pitfall):
  - Row dim == query dim → cosine as today.
  - Row dim != query dim → row skipped for *this query only*; counted in `meta.dim_mismatch_skipped` on the MCP envelope.
  - Zero candidates at query dim → `fail("transient", "embedding migration N% done; retry in 5m", retryable=true)`.
- `cos doctor` adds:
  - **C20** (`embedding.migration.status`) — green at 100% at 1024-dim.
  - **C21** (`embedding.dim_distribution`) — warn while a split exists; error if split persists > 7 days.
- Model-download failure (BGE-M3 ~560MB) → `fail("unavailable", …, retryable=true)`; migrator re-attempts with exponential backoff (capped 1h). Agent sessions continue on MiniLM with `meta.embedding_model="minilm-legacy"` until operator intervenes — **no silent degradation.**

### Pipeline invariants

- **Idempotent.** Running the pipeline N times on unchanged state yields zero writes.
- **Deterministic.** Same inputs → same `uid`s → same edges. Required for golden tests.
- **Partial-failure-safe.** A broken tree-sitter parse for one file does not abort the pipeline. Log to `.coding-os/.graph-parse-errors.log`, emit `extractor_error` node, continue.

---

## 7. Symbol Resolution Engine — The Hard Core

### 7.1 Why this is hard

Regex finds names. It does not answer *"which definition did this call resolve to?"*. graph-tool's answer is the 7-step lookup + evidence scoring. We copy that exactly.

### 7.2 Edge cases we handle at ship

- **Method override in diamond inheritance** — C3 MRO walk. Default: Python C3, TS `extends` chain, Go interface satisfaction.
- **Field type chain** — `user.address.city.getName()` resolves via `TypeBinding(user, User) → User.address:Address → Address.city:City → City.getName`.
- **Decorator-wrapped functions** — `@staticmethod def foo()` still emits `defines(foo)`. The decorator emits a separate `is_decorated_by` edge.
- **Re-exports** — `from .utils import foo` in an `__init__.py` + external `from pkg import foo` resolves through the re-export. Weight slightly reduced.
- **Python name shadowing** — `def foo(): foo = bar; foo()` — scope chain gives local `foo` precedence.
- **TS generics** — `getUser<T>(id): T` — without LSP, generic resolution is approximate. Confidence ≤ 0.6. LSP adapter (opt-in) raises to 0.95.

### 7.3 Known limits at ship (documented as edge-case tests)

- **Dynamic imports** — `importlib.import_module(name)`, `require(expr)` — missed. Not fixable without runtime tracing.
- **Monkey-patches** — `module.foo = bar` at runtime — missed.
- **Circular imports** — two edges emitted, viewer renders with `↻` badge.
- **String-based dispatch** — `getattr(obj, "method_" + variant)()` — missed. Skill: `graph-explorer` skill warns the agent when it sees this pattern.

### 7.4 LSP overlay (default ON — enterprise precision target ≥95%)

**Runtime topology — one shared server per language, not per-worker.**

- A single long-lived `pyright --outputjson --watch` subprocess and a single `tsserver` subprocess are owned by the orchestrator (§13), not spawned per indexer worker. All workers communicate with them via a Unix domain socket (`.coding-os/.lsp/<language>.sock`). This matches how production language servers are used (gopls, ruff-server).
  - Rationale: pyright cold-start on a large repo is 30–60s. Per-worker spawn across 8 workers × 50 batches = 20+ minutes of pure LSP startup cost. Shared server = one startup, amortized.
- **Warm-start role.** On `cos graph-reindex` (and on first server boot in `indexer:graph-os`), a dedicated role `lsp:warm-start` runs **before** indexer workers dispatch and blocks until the LSP process reports `initialized` and indexed `setup.py` / `pyproject.toml` / `tsconfig.json`. Warm-start is its own progress metric (`graph.lsp.warm_start.duration_ms`).

**Latency budgets (measured on 10k-file dogfood, I.5 ship gate).**

| Phase | Target |
|---|---|
| LSP warm-start (first boot) | ≤ 60s |
| LSP warm-start (resume, cache present) | ≤ 5s |
| Per-file symbol resolution (after warm-up) | P95 ≤ 5s |
| Per-file tree-sitter-only fallback | P95 ≤ 500ms |

**Precision overlay.**

- Parses the LSP server's symbol table and overlays onto our in-memory `SymbolTable`.
- LSP-provided resolutions **replace** tree-sitter resolutions where LSP confidence > tree-sitter confidence.
- Every overlay writes its own row to `graph_evidence_v12` (signal_name=`lsp_overlay`, weight=0.4, note=pyright version / tsserver version). An edge that was previously tree-sitter-only gets its confidence raised when LSP agrees.

**Circuit breaker & degrade path.**

- If LSP crashes or times out >3 times in 60s, the overlay is disabled for 5min and workers proceed tree-sitter-only. Logged to `.coding-os/.graph-lsp.log`; surfaced by `cos_graph_health()` as `lsp.state="degraded"`.
- If LSP warm-start exceeds 120s, the orchestrator emits a warning and indexer workers proceed tree-sitter-only for the first batch (confidence ≤ 85%); the LSP overlay re-attaches on the next batch.
- Toggle-off for constrained environments: `.coding-os/rag-config.yaml::graph.lsp.enabled: false`.

**Target precision with LSP overlay: ≥95%** (measured via per-language golden test set in I.5/I.6 ship gates).

---

## 8. Indexing Strategy — Scale Matters

### 8.1 Initial index

- Full repo walk on first `cos graph-reindex`. Bound: **<60s per 10k files** on a single laptop (measured target).
- Progress bar + cancellable. Writes to a temp DB, atomic swap at end (no partial state visible to agents).

### 8.2 Incremental re-index (file save)

Hooked into the existing `auto-reindex-docs.sh` PostToolUse hook (Phase H).

**Critical path — must stay synchronous and tight.**

On Write/Edit of a file:
1. Compute new `content_hash`. If unchanged → exit.
2. Re-run Stages 2–4 (parse → scope → symbol-table) for that file. Budget: **≤ 100ms**.
3. Re-resolve references in Stage 5 using **tree-sitter-only** (no LSP). Budget: **≤ 100ms**. Edges are written with confidence ≤ 0.85.
4. Cascade: if the file's **exports changed**, queue dependents for re-resolve — scheduled but **not awaited** (see §8.3).
5. Update `graph_nodes`, upsert `graph_edges_v12`, write `graph_evidence_v12` rows.
6. Fire `cos_log_hook graph-reindex incremental`.

**Synchronous bound: ≤ 200ms P95 for single-file edit on 10k-file repo** (I.13 measured gate).

**Asynchronous overlay — LSP raises precision without blocking.**

The LSP overlay (§7.4) runs **fire-and-forget**. When the file save returns, `cos_graph_context(<file>)` immediately serves tree-sitter-only edges with `meta.lsp_overlay_pending=true`. When the overlay finishes (typically 500ms–5s later), edges are upserted to their LSP-raised confidences (≥0.95) and `meta.lsp_overlay_pending=false` on subsequent queries.

Agents that need guaranteed LSP-level precision before proceeding can opt in with a blocking helper:

```
cos_graph_wait_lsp(file_path, timeout_seconds=5)
  → ok({state: "ready" | "degraded" | "timeout"})
```

`enforce-rename-plan.sh` and `enforce-graph-context.sh` (§11) call `cos_graph_wait_lsp` before granting their exemption tokens on load-bearing files.

### 8.3 Cascade invalidation algorithm

```
When file F changes:
  old_exports := current nodes where file_path=F AND is_exported=true
  new_exports := stage_3(new_content)
  diff := symmetric_difference(old_exports, new_exports)
  if diff is empty:
    resolve references only inside F (cheap)
  else:
    dependents := files where any edge (_, F.symbol, 'imports') for symbol in diff
    if len(dependents) > cascade_max_files:
       # Fallback path — do not enqueue thousands of tasks
       log overflow to .coding-os/.graph-cascade-overflow.log
       mark graph as dirty (graph_meta.dirty=true)
       schedule background full re-resolve via orchestrator role `indexer:graph-os` with role_args={mode:"full-resolve"}
    else:
       walk dependents BFS-style up to cascade_max_depth hops
       queue reached files for Stage 5 re-resolve
```

**Configurable limits** (defaults chosen so `core/lib/common.py`–style central modules don't thrash the indexer):

```yaml
# .coding-os/rag-config.yaml
graph:
  cascade_max_files: 500     # queue at most 500 dependents per edit
  cascade_max_depth: 2       # BFS depth cap for transitive dependents
  cascade_overflow_policy: "full-resolve-bg"  # "full-resolve-bg" | "mark-stale"
```

**Observability:**
- `cos doctor` check **C22**: cascade overflows in the last 24h < 10.
- Metric `graph.cascade.overflow.count` (per day) tagged with the triggering file path.
- When `graph_meta.dirty=true`, `cos_graph_*` tools return `meta.graph_dirty=true` so agents know results may lag; they do not fail.

### 8.4 Background indexer (thinking-os role)

For Codex sessions (no PostToolUse), or for ad-hoc batch reindexing:

- A `thinking-os` agent role: `indexer:graph-os` (see §13).
- Triggered by `COS_BACKGROUND_INDEX=1` env or `make graph-reindex`.
- Lives under the same agent orchestrator that dispatches coding agents — NOT a Python multiprocessing pool.

### 8.5 Scale targets (EXTRAPOLATIONS — must be validated in I.13)

The table below lists **targets**, not measurements. The only data point actually benchmarked at the time this plan was written is the 10k-file dogfood on `coding-os` itself; the 100k / 500k figures are linear extrapolations. I.13 (see §19) is the gate that replaces each row with a measured number on a reference MacBook Pro M1 (16GB) with the parallel orchestrator from I.9 enabled. Rows marked 🅔 are extrapolations to be revised if measurements disagree by more than 30%.

| Repo size | Initial index | Incremental edit (sync) | Cross-file query | MCP roundtrip | Source |
|---|---|---|---|---|---|
| 1k files | <5s | <50ms | <20ms | <100ms | 🅔 |
| 10k files | <60s | <200ms | <80ms | <200ms | dogfood baseline |
| 100k files | <15min | <500ms | <300ms | <500ms | 🅔 |
| 500k files | <90min | <1s | <1s | <1s | 🅔 |
| >500k files | *Kùzu backend required (§12); SQLite fallback is out-of-SLO* | — | — | — | — |

**I.13 deliverable:** publish `docs/benchmarks/graph-os.md` (append-only) with measured numbers, commit SHA, hardware, and any target revisions. Extrapolated rows become measured rows, or the SLO changes. No "ship-and-pray" on unmeasured scale claims.

---

## 9. MCP Tool Surface — Eleven Tools (`cos_graph_*`)

All tools wrapped in `@safe_tool` + `ok(data)` / `fail(category, msg)` envelope (Rule 14). `data.meta.layer = "graph"` on every response.

### 9.1 `cos_graph_query(q, kinds?, limit=10, max_hops=2, confidence_min=0.3)`

- Hybrid search: FTS5 (label + signature + docstring) + embedding cosine + graph-walk expansion.
- RRF-merged top-K.
- Returns `[{uid, kind, label, file_path, start_line, confidence, path_to_query}]`.
- **When to use:** "find me functions that handle login" (conceptual/semantic).

### 9.2 `cos_graph_context(uid_or_name, direction='both', depth=1, include_content=False)`

- Given a symbol, return callers + callees + siblings (same class/module) + referenced docs.
- Grouped by `edge_type`. Optional inline source code.
- **When to use:** Before editing any non-trivial function. Mirrors graph-tool `context`.

### 9.3 `cos_graph_impact(uid, direction='downstream', depth=3, confidence_min=0.5)`

- Blast radius: what downstream code breaks if I change this? What upstream tasks/docs need updating?
- Groups by risk tier: `will_break` (confidence ≥ 0.9), `should_review` (0.5-0.9), `context` (<0.5).
- **When to use:** Before any governance edit. Mirrors graph-tool `impact`.

### 9.4 `cos_graph_detect_changes(scope='working', analyze_downstream=True)`

- Read `git diff` for the given scope (`working`, `staged`, `HEAD~1..HEAD`).
- Map each hunk to affected symbols.
- For each affected symbol, compute downstream impact.
- Output: `{files, symbols, downstream_tasks, risk_level}`.
- **When to use:** Pre-commit / pre-push check. `cos_graph_detect_changes` is the agent's PR self-review.

### 9.5 `cos_graph_trace(entry_uid, terminals=['return', 'exception'], max_steps=50)`

- Forward execution-flow walk from an entry point (e.g., a route handler). Follows `calls` edges until it hits terminal nodes.
- Output: ordered step list with branch points.
- **When to use:** Debugging — "what's the call path when the user hits `/api/login`?".

### 9.6 `cos_graph_similar(uid, top_k=5, confidence_min=0.5)`

- Semantic similarity over `graph_node_embeddings`. Cosine top-K.
- **When to use:** "show me functions similar to this one" (refactor planning, duplicate detection).

### 9.7 `cos_graph_references(uid, kinds=['calls','accesses_field','imports'])`

- All inbound edges to a node. Simple, fast, no walking.
- **When to use:** The `find all references` IDE primitive, exposed to the agent.

### 9.8 `cos_graph_path(source_uid, target_uid, max_hops=5)`

- Shortest path between two nodes in the graph. Returns the chain of edges.
- **When to use:** "how is the login handler connected to the User model?" — dependency archaeology.

### 9.9 `cos_graph_export(format='json'|'mermaid'|'dot', root_uid?, edge_types?, max_nodes=500)`

- Export a subgraph in the requested format. JSON = source of truth for the viewer.
- Mermaid/DOT are compatibility outputs (GitHub rendering, Graphviz).
- **When to use:** The `cos graph-viz` CLI, and agents who want a diagram in their response.

### 9.10 `cos_graph_rename_plan(uid, new_name, check_strings=True)`

- Produce a complete rename plan for a symbol — every location that must change, with risk assessment.
- Walks `references`, `calls`, `imports`, `accesses_field` edges for call sites.
- Walks `links_to`, `cites_heading` edges for doc references.
- Walks `tested_by` edges for test-file references.
- Grep-style scan for `string_literals` matching the old name (e.g. dynamic dispatch, log messages, config files) — `check_strings=True` by default.
- Scans docstrings + comments for mentions (`comment_mentions`).
- Returns:

```json
{
  "old_name": "validateUser",
  "new_name": "checkUserCredentials",
  "call_sites":       [{file, line, edge_confidence, snippet}],
  "doc_references":   [{file, line, heading, context}],
  "test_references":  [{file, line, test_name}],
  "string_literals":  [{file, line, context, risk: "high|medium|low"}],
  "comment_mentions": [{file, line, comment}],
  "config_files":     [{file, line, key, context}],
  "risk":             "medium",
  "suggested_order":  ["tests first", "implementation", "docs", "string literals last"],
  "confidence":       0.87
}
```

- **When to use:** Before any rename. Agents doing refactoring call this *first*. Without it, rename-via-grep misses non-obvious call sites (via re-exports, decorators, metaclass magic) and false-positive's on unrelated strings.
- **Token budget:** ~4k default / 10k hard cap (rename plans can be long).

### 9.11 `cos_graph_contracts(scope='all', kinds=['http', 'mcp', 'grpc', 'event', 'websocket'])`

- Extract first-class service contracts declared in the repo (API surface).
- Detects handlers via AST + decorator patterns per-language. The detector tracks **dynamic / generated** routes as first-class — not just static decorators.
  - **Python/Django:**
    - `urlpatterns = [path(...), ...]` + `re_path(...)` + `include(...)` (recurse into included router modules).
    - `@api_view(['GET', ...])` decorators.
    - **DRF `router.register(prefix, ViewSetClass)`** — the extractor walks `ViewSetClass.list/create/retrieve/update/partial_update/destroy` (plus `@action` decorated custom actions) and **synthesizes the 5–7 routes the router auto-generates**. Each synthesized route is tagged `derivation: "drf_router_register"` in metadata and has confidence 0.9 (not 1.0 — inferred from class inspection).
  - **Python/FastAPI:**
    - `@app.get`, `@app.post`, `@router.*` — literal path extraction.
    - **`app.include_router(sub_router, prefix="/v2")`** — recurse into `sub_router`'s routes and prefix-concat. Mount-point nesting is followed to arbitrary depth.
    - **Starlette `Mount("/static", app=...)`** — emitted as a sub-app boundary node, not a route.
  - **Python/Flask:** `@app.route`, `@blueprint.route`, `app.add_url_rule`, `Blueprint` register chain.
  - **TS/Next.js:**
    - `app/**/route.ts` exported `GET`/`POST`/... functions.
    - **Dynamic segments `[id]/page.ts`, `[...slug]/route.ts`, `[[...slug]]/page.ts`** — path normalized to `/{id}` / `/*slug` / `/**slug`; tagged `dynamic_segment: true`.
    - `pages/api/*` legacy handlers.
    - `app/**/layout.ts` and `app/**/middleware.ts` as non-route nodes linked via `wraps_route` edges to the routes they surround.
  - **TS/NestJS:** `@Controller('prefix')`, `@Get/@Post/@Put/@Patch/@Delete`, `@UseGuards`/`@UseInterceptors` emitted as separate edges.
  - **Go/Fiber:** `app.Get`, `app.Post`, `app.Group(prefix)` (recurse into group chain to reconstruct full paths).
  - **MCP tools:** `@mcp.tool(...)` decorators, `@safe_tool` wrappers.
  - **gRPC:** `.proto` files parsed for `service/rpc` declarations + server-side `RegisterXxxServer` calls for language bindings.
  - **Event handlers:** Celery `@task`, RQ, Kafka consumers, websocket `@sock.route`, Django signals (`@receiver`), Django Channels consumers.

**Unmatchable routes are still reported.** Dynamic fetch targets (`fetch(\`/api/\${id}\`)`), reflection-based dispatch, and runtime-registered routes are surfaced with `{kind: "opaque_route", reason: ...}` so agents know the surface is incomplete rather than seeing silent gaps.
- Returns a unified contract surface:

```json
{
  "http_routes":     [{method, path, handler_uid, file, line, auth_required, params_schema}],
  "mcp_tools":       [{name, handler_uid, schema, description, file, line}],
  "grpc_endpoints":  [{service, method, request_type, response_type, handler_uid}],
  "event_handlers":  [{event_name, queue, handler_uid, file}],
  "websocket":       [{path, handler_uid, events}]
}
```

- **When to use:**
  - F3 Step 4 (API Design review) — *"list every endpoint"*
  - F8 Layer 1 (Auth audit) — *"does every endpoint check auth?"* cross-reference with `cos_graph_references` on `verify_auth()`.
  - Documentation generation — auto-produce API reference.
- **Token budget:** ~3k default / 10k hard cap (full contract surface of a large service).

### 9.12 Retires the legacy `cos_graph`

`cos_graph` (migration v4, `co_edit` only) becomes a thin shim over `cos_graph_context` with `edge_types=['co_edit']` for 1 release, then removed.

### Token budget per tool (defaults)

| Tool | Default response size | Hard cap |
|---|---|---|
| `_query` | ~1.5k tokens (10 results × 150 tokens) | 4k |
| `_context` | ~2k (20 edges + metadata) | 6k |
| `_impact` | ~3k (grouped risk tiers) | 8k |
| `_detect_changes` | ~2k | 6k |
| `_trace` | ~2k (50 steps) | 8k |
| `_similar` | ~800 | 2k |
| `_references` | ~1k | 3k |
| `_path` | ~500 | 2k |
| `_export` | variable (json/mermaid) | 20k (warns) |
| `_rename_plan` | ~4k (plan tables) | 10k |
| `_contracts` | ~3k (endpoint table) | 10k |

---

## 10. Integration with `thinking-os`

### 10.1 Shared DB, shared embeddings

- Same SQLite file (`$COS_DB_PATH`), migration v12 (next append-only slot after v11).
- Same `embeddings.py` (MiniLM-L6-v2). No new model load.
- `cos_search` (memory) can blend graph edges as a retrieval signal — added in Phase J.

### 10.2 Registered via the same MCP server

- `core/thinking_os/server.py` imports `tools/graph.py` alongside existing 7 modules.
- `cos_health` reports graph statistics: node count, edge count, last re-index time, parse error rate.

### 10.3 Does NOT live under `core/thinking_os/`

New directory `core/graph-os/` — parallel peer, not a subdirectory. Importable as `graph_os.*` from Python.

---

## 11. Integration with Hooks & Skills

### 11.1 Hook: auto-reindex-graph (extends Phase H)

- Lives at `core/hooks/auto-reindex-docs.sh` (rename to `auto-reindex-artifact.sh`, or extend in-place).
- On Write/Edit of any file: call the appropriate extractor. Docs stay in `doc_indexer`; code goes through the graph-os pipeline.
- **Decision:** extend in-place. New function `reindex_graph_for_file()` in the shared shell script.

### 11.2 Hook: enforce-graph-context (new, PreToolUse on Edit)

- **Scope is data-driven**, not hardcoded in the shell script. The hook reads `.coding-os/rag-config.yaml::graph.enforce_context_on` (a list of glob patterns). Example:

  ```yaml
  graph:
    enforce_context_on:
      - "core/thinking_os/server.py"
      - "core/thinking_os/db.py"
      - "core/thinking_os/tools/*.py"
      - "cli/main.py"
      - "templates/_base/AGENTS.template.md"
  ```

  Consumer projects get a sensible default list generated by `cos init`; this list is then maintained by the project as `graph-os` learns the repo's load-bearing files.
- Before a matching `Edit`, the hook checks whether `$COS_AGENT_DIR/.graph-context-<uid>` marker exists for the target file. Marker is created by `cos_graph_context` on the file.
- If the marker is missing, the hook **warns** (does not block) by default. Strict mode (`COS_ENFORCE_GRAPH_CONTEXT=strict`) promotes the warning to a block.
- Opt-in toggle: `COS_ENFORCE_GRAPH_CONTEXT=1` activates warn mode; unset disables the hook.

### 11.3 Skill: `graph-explorer` (new)

- `core/skills/graph-explorer/SKILL.md`.
- Mirrors `codebase-explorer` but graph-powered. Triggers: "understand this module", "trace this call", "what depends on X".
- First retrieval: `cos_graph_context`. Second: `cos_graph_impact`. Third: `cos_search` for past observations.

### 11.4 Skill: `codebase-explorer` — update

- Add a Gate: before grep, if query is a symbol, try `cos_graph_query` first. It's faster and more accurate for named symbols.

### 11.5 CLI: `cos graph-*` commands

**Indexing & status:**
- `cos graph-reindex` — full re-index (current repo).
- `cos graph-reindex --incremental <path>` — single file.
- `cos graph-reindex --cancel` — stop all indexer workers cleanly.
- `cos graph-stats` — node/edge counts, parse errors, backend, index freshness.

**Querying:**
- `cos graph-query "<natural language query>"` — hybrid search from the terminal.
- `cos graph-context <uid>` — quick context dump.
- `cos graph-impact <uid>` — blast radius CLI.
- `cos graph-contracts [--kind http|mcp|...]` — list API surface.

**Viewer & export:**
- `cos graph-viz [--root <uid>] [--edge-types ...] [--depth 2] [--open] [--bundled]` — Sigma.js WebGL viewer.
- `cos graph-export --format mermaid|dot|json --out diagram.md` — static diagram.

**Ingestion flexibility (onboarding):**
- `cos graph-index-local <path>` — index any local folder (not just current repo).
- `cos graph-index-github <url> [--branch main] [--alias my-repo]` — clone (shallow) to `~/.coding-os/remote-repos/<alias>/`, index.
- `cos graph-index-zip <archive.zip> [--alias onboarding]` — extract + index.
- All ingestion modes use the same pipeline — the graph is indistinguishable from a local clone.

**Repo groups (§17):**
- `cos graph-group create <name>`
- `cos graph-group add <group> <path> [--alias <alias>]`
- `cos graph-group remove <group> <alias>`
- `cos graph-group list`
- `cos graph-group status <group>`
- `cos graph-group sync <group>` — re-index all members.
- `cos graph-group query <group> "<q>"`
- `cos graph-group contracts <group>`
- `cos graph-group viz <group> [--open]`

### 11.6 Doctor check

- `cos doctor` adds check C16: `graph_last_index_age_seconds < 3600` (warns if stale).
- Check C17: `graph_parse_error_rate < 0.05`.

---

## 12. Storage Architecture — Two Specialized Stores

### 12.1 Primary: Kùzu (graph) + SQLite (metadata)

```
.coding-os/
├── thinking-os.db     ← SQLite: observations, learned_patterns, doc_chunks, tasks, metrics
└── graph-os.kuzu      ← Kùzu: graph_nodes, graph_edges, graph_node_embeddings, HNSW vector index
```

**Why two stores, not one:**

- **SQLite** is optimal for: FTS5 text search, metric tables, time-series observations, simple key-value task metadata. Proven in our 1083-test suite.
- **Kùzu** is optimal for: graph walks (BFS, shortest-path, k-hop expansion), Cypher query, HNSW vector search on embeddings. 10-100× faster than SQLite for these workloads.

Cross-reference between stores via `uid` (stable string ID, e.g. `code:method:app/user.py::User.get_name`). An agent rarely queries both in one call; when it does, MCP tools join at the Python layer (`cos_graph_context` pulls graph from Kùzu + pulls docstring/observations from SQLite).

### 12.2 Backend Protocol (`graph_os/backend.py`)

```python
class GraphBackend(Protocol):
    def insert_node(self, node: GraphNode) -> None: ...
    def insert_edge(self, edge: GraphEdge) -> None: ...
    def query_edges(self, source_uid: str, edge_types: list[str] | None = None, limit: int = 100) -> list[GraphEdge]: ...
    def walk_bfs(self, root_uid: str, max_hops: int, edge_types: list[str] | None = None) -> list[GraphNode]: ...
    def shortest_path(self, source_uid: str, target_uid: str, max_hops: int = 5) -> list[GraphEdge]: ...
    def vector_search(self, query_vec: list[float], top_k: int = 10, kind_filter: str | None = None) -> list[tuple[GraphNode, float]]: ...
    def export_subgraph(self, root_uid: str, max_nodes: int = 500) -> dict: ...
```

### 12.3 Implementations

- `graph_os/backends/kuzu_backend.py` — **primary, default**. `pip install kuzu` (Apache 2.0, embedded, single file). Uses Cypher for all graph walks. HNSW index on `graph_node_embeddings.vector`.
- `graph_os/backends/sqlite_backend.py` — **fallback**. Used when Kùzu binary is unavailable (e.g. unusual architectures, tests running without Kùzu). Functionally equivalent but ≥10× slower on graph walks. Selected automatically via `KuzuBackend.is_available()` check at startup.

### 12.4 Configuration

```yaml
# .coding-os/rag-config.yaml
graph:
  backend: auto              # "auto" | "kuzu" | "sqlite"
  kuzu_path: .coding-os/graph-os.kuzu
  embedding_model: BAAI/bge-m3
  embedding_dim: 1024
  lsp:
    enabled: true
    python: pyright
    typescript: tsserver
```

### 12.5 Backend-agnostic tool surface — fail loud, not silent

The MCP tool surface is backend-agnostic at the **type** level (same inputs, same envelope shape), but **failure is explicit**.

- Normal path: a MCP call hits the configured backend (auto → Kùzu if installed, else SQLite). `data.meta.backend = "kuzu" | "sqlite"` is always populated so the agent can reason about precision and latency.
- Kùzu configured but Kùzu runtime crashes or the file is corrupt:
  - The tool returns `fail("unavailable", "graph backend offline; SQLite fallback available — pass backend='sqlite' to retry", retryable=true)`.
  - **No silent fallback.** Silently serving SQLite results when the agent asked for Kùzu would hide latency regressions — a 10× slowdown on `_impact depth=3` mid-session.
- Operator can force a backend per-call: `cos_graph_context(uid, backend="sqlite")` — useful for debugging and parity tests.
- **Configuration drift guard:** on MCP server boot, the backend health probe is stored in `.coding-os/.graph-backend.json` (`{backend, kuzu_version, sqlite_schema_version, last_ok_at}`). `cos doctor` check **C18** fails if the probe is stale > 6h or shows `backend_mismatch`.

### 12.6 Parity matrix — 100+ scenarios, not 50

I.0's ship gate requires that `KuzuBackend` and `SqliteBackend` return **identical results** across a parity matrix of ≥ 100 scenarios. The matrix is the cross product of:

| Axis | Values |
|---|---|
| Tool | `_context`, `_impact`, `_trace`, `_path`, `_references`, `_similar`, `_query` (7) |
| Depth | 1, 2, 3 |
| Confidence floor | 0.3, 0.6, 0.9 |
| Fixture | empty graph, tiny (10 nodes), medium (1k nodes) |

That is 7 × 3 × 3 × 3 = 189 base scenarios. Every cell runs twice: once with each backend, result diff'd. Known asymmetries (Kùzu is faster; SQLite approximates recursive CTEs) are asserted **as specific tolerances** — not hand-waved.

A subset (25 scenarios) uses `cos_graph_trace` which exercises Cypher-style recursion. For those, the SQLite backend is allowed ≥ 3× higher latency but must return the identical result set. If it cannot, the scenario is documented as a known SQLite limitation in the ship gate notes — and the corresponding MCP call emits `meta.sqlite_approximation=true` at runtime.

---

## 13. Multi-Agent Integration — Fully Implemented Orchestrator

### 13.1 Architecture

The orchestrator is a first-class subsystem under `core/thinking_os/orchestrator/`, shipped in Phase I (not deferred to Phase J).

```
core/thinking_os/orchestrator/
├── registry.py          # role catalog — which roles exist, what each does
├── dispatcher.py        # routes a task to the right role, with priority/retry
├── worker_pool.py       # manages subprocess workers (not multiprocessing.Pool — real agent processes)
├── progress.py          # cos_metric_record wrapper for role-keyed metrics
└── roles/
    ├── __init__.py
    ├── indexer_graph_os.py   # ← ships in Phase I
    └── (other roles in Phase J)
```

### 13.2 `indexer:graph-os` role — full implementation

- Role definition: input = `FileTask | FileBatchTask`, output = `{nodes_written, edges_written, parse_errors, duration_ms}`.
- Executable: `python -m graph_os.indexer.run --file <path> --role-id indexer:graph-os`.
- Invoked by the dispatcher — never directly by hooks.
- Fire-and-forget: hooks post a task to the dispatcher; dispatcher queues for the next available indexer worker.

### 13.3 Parallel dispatch

- Worker pool size: `min(cpu_count, 8)` by default. Configurable via `COS_INDEXER_POOL_SIZE`.
- For initial reindex of a large repo: dispatcher splits the file list into ~N/pool_size batches, one per worker.
- Incremental: each file save → one task → one worker. No batching.
- Cancellation: `cos graph-reindex --cancel` sends SIGTERM to all indexer workers cleanly.

### 13.4 Health + progress

- Progress metrics: `graph.indexer.files_processed`, `graph.indexer.queue_depth`, `graph.indexer.worker_utilization`.
- Agent visibility: `cos_graph_health()` reports indexer pool state.
- On worker crash: dispatcher restarts up to 3 times, then quarantines the offending file with a `parse_quarantine=true` node.

### 13.5 Formula-role alignment (roles that CONSUME the graph, Phase J)

Phase J will map `thinking-os` agent roles to the personas in `formulas-en.md § Role-Based Entry Points`:

| thinking-os role | Formula persona | Primary graph tools |
|---|---|---|
| `agent:backend-dev` | Go/Python Backend | `_context`, `_impact`, `_detect_changes` |
| `agent:frontend-dev` | React Native / Next.js | `_context`, `_trace` (component tree) |
| `agent:architect` | Tech Lead | `_export`, `_impact`, `_similar` |
| `agent:qa` | QA Engineer | `_detect_changes`, `_trace` |
| `agent:devops` | DevOps | `_query` (routes, handlers) |
| `agent:reviewer` | Code Review | `_detect_changes` pre-merge |
| `indexer:graph-os` | — (infrastructure role) | writes only, no reads |

**Phase I ships:** full orchestrator + `indexer:graph-os` role (operational). **Phase J ships:** the six agent-consumer roles above (they read the graph; the graph already exists).

---

## 14. Integration with the 11-Formula Framework

graph-os isn't just infrastructure; it is a **load-bearing input to every one of the 11 formulas**. The Role-Based Entry Points in [`formulas-en.md § Role-Based Entry Points`](./code-os-core-docs/thinkingos-formulas/formulas-en.md#L887) assign ownership of F1–F11 across Architect, Backend, Frontend, QA, DevOps, and Reviewer personas. For each persona, graph-os supplies the deterministic substrate that would otherwise come from grep + guess.

| Formula | Step | How graph-os contributes |
|---|---|---|
| **F1 — Research & Discovery** | Step 2 (Architectural Exploration) | When docs are thin, `cos_graph_context(entry_point)` reverse-engineers the live architecture: routes → handlers → services → models. Architect persona runs this before proposing refactors. |
| **F2 — Analysis** | Step 10 (Dependency Map) | `cos_graph_impact` gives the exact dependency DAG, not an imagined one. |
| **F3 — Architecture** | Step 4 (API Design) | `cos_graph_references` on public handler functions surfaces who calls what externally. |
| **F4 — Technical Documentation** | Step 3 (API Reference Generation) | `cos_graph_contracts(scope="all")` enumerates every HTTP/MCP/gRPC/event handler for auto-generated API reference. The doc generator consumes this directly — no manual `endpoints.md` drift. |
| **F5 — Implementation** | Step 1 (Pre-Implementation Verification) | Agent must call `cos_graph_context` before editing — hooked via `enforce-graph-context`. |
| **F6 — Testing** | Section A Layer 2 (Integration) | `cos_graph_detect_changes` produces the diff-→-risk map that drives regression test selection. |
| **F7 — Debugging** | Step 2 (Isolate Fault Location) | `cos_graph_trace` walks call chain from entry point to fault. |
| **F8 — Security Audit** | Layer 1 (Auth) | `cos_graph_query("handles_route") + graph_references` lists every endpoint + who calls `verify_auth()` — a declarative auth coverage audit. |
| **F9 — Deployment & DevOps** | Step 3 (Pre-Release Checks) | `cos_graph_contracts(scope="all")` + `cos_graph_detect_changes(scope="HEAD~1..HEAD")` run in CI as the *API-surface diff* — any new/removed endpoint fails the release gate unless explicitly approved. DevOps persona owns this check. |
| **F10 — Monitoring** | Step 2 (Tracing) | `cos_graph_trace` produces synthetic trace diagrams for distributed-trace setup. |
| **F11 — Refactoring** | Step 1 (Debt Identification) | `cos_graph_similar` + `cos_graph_impact` surface hotspots and coupling. |

**Principle:** every formula that an enterprise engineer reaches for — research, analysis, architecture, docs, implementation, testing, debugging, security, deployment, monitoring, refactoring — has a graph-os retrieval as its factual anchor. Prose reasoning rides on top of graph truth, not vice versa.

Concrete: Formula 5 Step 1 requires the agent to "reference scenarios from the Problem Decomposition formula" + "explicit inputs, dependencies". The `Pre-Implementation` phase becomes mechanical: the agent invokes `cos_graph_context <file_or_symbol>` and receives — in one MCP call — all callers, docs, specs, test files, and adjacent symbols. The formula is satisfied by the graph, not by prose reasoning.

---

## 15. Viewer — `cos graph-viz` (Sigma.js + Graphology, WebGL)

### 15.1 Architecture — WebGL for industrial scale

- CLI: `cos graph-viz [--root <uid>] [--edge-types ...] [--depth 2] [--open] [--layout forceAtlas2|circular|random]`.
- Generates a self-contained HTML file with embedded JSON graph.
- **Rendering stack:**
  - **[Sigma.js](https://www.sigmajs.org/) (v3.x)** — WebGL graph renderer. Handles 50,000+ nodes smoothly; D3/SVG chokes at ~1,000.
  - **[Graphology](https://graphology.github.io/)** — graph data structure + algorithms (BFS, shortest-path, community detection) shared between viewer and exporter.
  - **ForceAtlas2** layout worker — scientifically-validated force-directed algorithm (Gephi origin); runs off-main-thread in a Web Worker.
- **Why not D3:**
  - D3 uses SVG → one DOM element per node. Browser reflow cost is O(n²) past ~1k nodes.
  - For enterprise repos (`cos_graph_impact` on a popular module can return 5k+ related nodes), WebGL is the only path.
  - Sigma.js + Graphology is also the stack graph-tool uses — proven at industrial scale.
- Controls: search, filter by edge type, hover-for-details, click-to-focus, right-click-to-remove, **zoom-to-fit**, **Leiden community colouring**, **minimap** for large graphs.
- Colours: `doc`=blue, `code`=green, `task`=orange, `cos:skill/hook/rule/tool`=purple; broken edge=red dashed; community-coloured when `--color-by community`.
- Accessible: keyboard navigation, ARIA labels, respects `prefers-reduced-motion`, screen-reader-friendly node list as a fallback when WebGL unavailable.

### 15.1.1 Dependencies (pinned CDN, integrity-hashed) + CSP

```html
<!-- Self-contained: pinned versions + SRI hashes, no npm build -->
<meta http-equiv="Content-Security-Policy" content="
  default-src 'none';
  script-src 'nonce-__NONCE__' https://cdn.jsdelivr.net;
  style-src 'nonce-__NONCE__';
  img-src 'self' data:;
  connect-src 'self';
  font-src 'self';
  base-uri 'none';
  frame-ancestors 'none';
">
<script nonce="__NONCE__"
        src="https://cdn.jsdelivr.net/npm/graphology@0.25.4/dist/graphology.umd.min.js"
        integrity="sha384-..."></script>
<script nonce="__NONCE__"
        src="https://cdn.jsdelivr.net/npm/graphology-layout-forceatlas2@0.10.1/worker.umd.min.js"
        integrity="sha384-..."></script>
<script nonce="__NONCE__"
        src="https://cdn.jsdelivr.net/npm/sigma@3.0.0/dist/sigma.min.js"
        integrity="sha384-..."></script>

<!-- Graph data lives in JSON block, NEVER inlined into a <script> -->
<script type="application/json" id="graph-data">__GRAPH_JSON__</script>
```

**Security contract:**
- Every page load generates a fresh `__NONCE__` (128-bit URL-safe) via `secrets.token_urlsafe(16)` in the exporter. Nonce is shared between `<meta>` CSP and every legitimate `<script nonce=...>` / `<style nonce=...>`.
- Graph payload is **always** served through a `<script type="application/json">` block and parsed via `JSON.parse(document.getElementById('graph-data').textContent)` in the viewer's bootstrap script. Never via template interpolation into executable JS.
- All label / signature / docstring strings are written through `el.textContent = …` — never `innerHTML`. An I.10 unit test asserts zero `.innerHTML` assignments in `viewer/bootstrap.js`.
- `--bundled` offline mode replaces `https://cdn.jsdelivr.net` in the CSP with `'self'` and inlines the scripts; the nonce requirement is preserved so even air-gapped bundles reject foreign script injection.

### 15.1.2 I.10 security ship gate

- CSP auditor test: parse the exported HTML through `python -c "import csp_parser; assert csp.default_src == ['none']"` (or equivalent). Fails if any directive is missing or relaxed.
- XSS fuzz test: inject `<img src=x onerror=alert(1)>` into a node label; assert it renders as literal text.
- Nonce-uniqueness test: generate two exports back-to-back; assert nonces differ.

### 15.2 Output example

```
╭────────────── coding-os graph (root: cos_graph_impact) ─────╮
│                                                              │
│   docs/phase-i-knowledge-graph-plan.md                       │
│        │ links_to                                            │
│        ▼                                                     │
│   core/graph-os/server.py                                    │
│        │ contains                                            │
│        ▼                                                     │
│   cos_graph_impact(uid, direction, depth)  ◄── focus         │
│        │ calls                                               │
│        ├──► walk_bfs()  (graph_os/backend.py)                │
│        ├──► load_evidence()                                  │
│        └──► _shared.ok(data)                                 │
│                                                              │
│   [search]  [edge types ▼]  [depth: 2]  [export JSON]        │
╰──────────────────────────────────────────────────────────────╯
```

### 15.3 Viewer scale guardrail (WebGL — raised ceilings)

- **Smooth zoom/pan up to 10,000 nodes** (Sigma WebGL baseline).
- **Hard cap 50,000 nodes** with progressive rendering + level-of-detail (hide labels when zoomed out, cluster nodes at high zoom-out).
- Beyond 50k → the viewer suggests a `--focus <uid>` subgraph view. Agents exporting huge graphs see a warning in the MCP envelope (`meta.viewer_may_lag=true`).

---

## 16. Token & Accuracy Optimization

### 16.1 Token budgets (defaults tuned for agent sessions)

- Every tool returns ≤4k tokens by default. Override via explicit params.
- Pagination: `cursor` token on every response; `next_step_hint` when truncated.
- Implicit pruning: edges with `confidence < confidence_min` omitted.
- Content elision: `include_content=False` by default; only signature + line range.

### 16.2 Accuracy levers

- **Tier 0 (always):** tree-sitter + scope extractor + 7-step lookup. Baseline ≥80% precision on Python / TS.
- **Tier 1 (opt-in):** LSP escalation (pyright, tsserver). Target ≥95%.
- **Tier 2 (Phase J):** runtime trace instrumentation — truth for dynamic dispatch.
- **Evidence model:** every agent decision is confidence-aware. No silent wrong answers.

### 16.3 Failure modes + fallbacks (for agents)

- `cos_graph_query` returns `meta.backend="sqlite-fts-only"` if embeddings are unavailable (no `rag` extra installed). Agent knows to broaden its search.
- `cos_graph_impact` returns `meta.confidence_distribution` so the agent can judge how much to trust the result.
- If the graph hasn't been indexed yet (first run), tools return `fail("unavailable", "graph not indexed; run cos graph-reindex")` with `retryable=true` once indexing completes.

---

## 17. Multi-Repo & Repo Groups

Modern products cross repo boundaries: a "platform" is frontend + backend + AI-service + mobile + infra, each a separate repo. graph-os supports this first-class via **repo groups**.

### 17.1 Per-repo isolation (baseline)

- Each repo has its own `.coding-os/graph-os.kuzu`. No shared state by default.
- `cos_graph_*` tools accept optional `repo` param — defaults to current working dir, resolves aliases from `~/.coding-os/registered-repos.json`.

### 17.2 Groups — cross-repo queries

A **group** is a named set of repos that conceptually belong together (e.g. `my-platform = frontend + backend + ai-service`). Groups have their own aggregated graph view + cross-repo edge detection.

```bash
# Group lifecycle
cos graph-group create my-platform
cos graph-group add my-platform /path/to/frontend --alias frontend
cos graph-group add my-platform /path/to/backend --alias backend
cos graph-group add my-platform /path/to/ai-service --alias ai
cos graph-group remove my-platform old-repo
cos graph-group sync my-platform                    # index all members

# Group queries
cos graph-group list
cos graph-group status my-platform                  # member health, index freshness
cos graph-group contracts my-platform               # API contracts across all members
cos graph-group query my-platform "validateUser"    # search all members
```

### 17.3 Cross-repo edges — inferred vs declared, with ownership

When `cos graph-group sync` runs, the group's aggregate indexer detects:

- **HTTP contract edges** — frontend `fetch('/api/users')` → backend handler `@app.route('/api/users')`. Edge type: `calls_contract`. **Default confidence 0.6** (inferred). Raised to **0.95** only if the backend repo declares ownership (see below).
- **MCP tool edges** — agent-side code that invokes `cos_graph_query` → the `@mcp.tool("cos_graph_query")` handler in `server.py`. Edge type: `calls_mcp_tool`. Confidence 0.95 (name is a unique string across the ecosystem).
- **gRPC / proto-shared types** — both repos include the same `.proto` file → `shares_proto` edges. Confidence 0.9.
- **Config/env cross-refs** — `.env.example` keys read by multiple repos → `shares_config` edges. Confidence 0.5 (heuristic; common key names recur).

These edges persist in the **group-level Kùzu DB** at `~/.coding-os/groups/<group-name>/graph.kuzu`, NOT in any individual repo's DB. Per-repo DBs stay pure.

#### Ownership declaration disambiguates overlapping routes

When a group has two backends exposing `/api/users` (common in platform splits), confidence-0.6 inferred edges from every frontend to every backend handler would be misleading. Each member can declare owned surfaces in `.coding-os/group-membership.yaml`:

```yaml
# repos/backend-users/.coding-os/group-membership.yaml
group: my-platform
alias: backend-users
owns:
  http_routes:
    - "/api/users"
    - "/api/users/*"
    - "/internal/users/**"
  mcp_tools: []     # no MCP tools exposed
  event_topics:
    - "users.*"
```

Behavior:
- Route matches a declared owner → `calls_contract` edge targets **only** that owner's handler; confidence **0.95**.
- Route matches no declared owner → inferred edges to all plausible handlers; confidence **0.6**; tagged `meta.ambiguous=true`.
- Two members both declare ownership of the same route → group sync fails with a clear conflict error. Resolve by editing `group-membership.yaml`.

#### Dynamic fetch targets

`fetch(\`/api/\${dynamicId}\`)` and similar template-literal paths cannot be pointed at a specific handler. The extractor emits a `calls_contract_dynamic` edge to a synthetic node representing "any route matching this prefix" with confidence 0.3 and `meta.dynamic=true`. Agents doing rename-plan work see these flagged explicitly.

#### I.12 false-positive audit (ship gate)

Fixture: three repos (`frontend`, `backend-a`, `backend-b`) where both backends expose `/api/users`.
- Without ownership declaration: frontend `fetch('/api/users')` emits two inferred edges, confidence 0.6 each, `meta.ambiguous=true`. Assertions check count and metadata.
- With `backend-a` declaring ownership: exactly one edge, to `backend-a`, confidence 0.95. Assertion: no edge to `backend-b`.
- With conflicting declarations: `cos graph-group sync` returns non-zero and prints a machine-readable conflict report.

### 17.4 Group MCP surface

All `cos_graph_*` tools accept a `group` param as alternative to `repo`:

```python
cos_graph_query("validateUser", group="my-platform")
# Searches frontend + backend + ai, returns results tagged by origin repo.

cos_graph_contracts(group="my-platform")
# Lists every route/tool/handler across all members in one envelope.

cos_graph_impact(uid="...", group="my-platform", direction="downstream")
# Blast radius spans repos — e.g. renaming a backend route shows all frontend fetch calls.
```

### 17.5 Group observability

- `cos doctor` check C19: all group members reachable + indexed + fresh.
- Metrics: `graph.group.<name>.member_count`, `graph.group.<name>.cross_edges_count`, `graph.group.<name>.last_sync_ms`.
- Group-level viewer: `cos graph-viz --group my-platform` — each repo becomes a supernode cluster in the visualization.

---

## 18. Observability & Health

- Metrics emitted via `cos_metric_record`:
  - `graph.index.duration_ms` (per run)
  - `graph.index.files_processed`
  - `graph.index.parse_errors`
  - `graph.query.duration_ms` (per `cos_graph_*` call, tagged by tool)
  - `graph.db.size_bytes`
  - `graph.nodes.count`, `graph.edges.count`
- `cos_graph_health()` MCP tool — summary for the agent: "graph is fresh (2m old), 12,341 nodes, 45,892 edges, 0.2% parse errors."
- Logs: `.coding-os/.graph.log` (indexer), `.coding-os/.graph-parse-errors.log` (per-file errors).
- Integrated with `cos doctor` (checks C16 + C17 + C18 = backend reachable).

---

## 19. Roadmap — Fifteen Slices

Execution order rearranged to deliver a minimum-viable agent-usable graph after I.3, full code graph with LSP precision after I.6, then layer scale + ergonomic value.

Each slice's ship gate now carries an explicit **minimum test count** and references the tightened DoD from earlier sections (parity matrix §12.6, CSP hardening §15.1.1, ownership declaration §17.3, size guards §13 below).

| Slice | Scope | LOC | Min tests | Ship gate | Dependencies |
|---|---|---|---|---|---|
| **I.0** | Migration v12 (`graph_nodes`, `graph_edges_v12`, `graph_evidence_v12`, `graph_nodes_fts`) + `embedding_dim` column add to legacy `embeddings` table (v12b) + Kùzu schema init + `backend.py` Protocol + both `backends/kuzu_backend.py` AND `backends/sqlite_backend.py` | ~800 | ≥ 40 | migration round-trip test (v11 → v12 then rollback simulation) + backend-parity matrix (≥ 189 scenarios, §12.6) + determinism golden test (same inputs → byte-identical rows across 3 runs) | — |
| **I.1** | Embedding migration as a **background role**: `scripts/migrate_embeddings_minilm_to_bge_m3.py` + new `migrator:embeddings` orchestrator role + `embeddings.py` upgraded to BGE-M3 (1024-dim) with `embedding_dim`-aware `cosine_similarity` + `graph_node_embeddings` in Kùzu + `.coding-os/.embedding-migration.json` checkpoint | ~500 | ≥ 25 | existing 109 RAG tests still pass + Persian query precision measured vs baseline + **dim-mismatch handling test** (no silent `[]` returns) + **resume-after-crash test** | I.0 |
| **I.2** | `graph_os/extractors/md_links.py` — markdown link + wikilink + frontmatter `ssot_of:` extractor. Heading-scoped (`cites_heading`) AND file-scoped (`links_to`) edges. Wired into `auto-reindex-docs.sh` | ~280 | ≥ 30 | extractor unit tests (fixtures per link style) + hook integration test + both edge types present in dogfood run | I.0 |
| **I.3** | `graph_os/extractors/task_deps.py` — task-dependency edges + task→doc `references_doc` edges + git-derived `produces_code` edges. Backfill + incremental | ~250 | ≥ 20 | backfill test + incremental test + 50k-task benchmark | I.0, existing Phase C |
| **I.4** | `graph_os/extractors/code_python.py` — full tree-sitter Python extractor + 5-pass scope extractor + symbol table + 7-step lookup (copied from graph-tool, adapted) | ~1000 | ≥ 50 | resolution precision ≥ 85% on `coding-os` itself (golden test set: 200 calls) + edge cases (circular imports, re-exports, type chains, method override, C3 MRO) + negative tests (syntax errors do not abort pipeline) | I.0 |
| **I.5** | `graph_os/lsp_overlay.py` + **shared** pyright subprocess (Unix-domain socket, §7.4) + `lsp:warm-start` orchestrator role + circuit breaker — Python precision boost to ≥95% | ~450 | ≥ 25 | precision ≥ 95% on golden set + graceful-degrade test (SIGKILL pyright mid-index) + warm-start latency (≤ 60s cold / ≤ 5s warm) | I.4 |
| **I.6** | `graph_os/extractors/code_ts.py` + `code_tsx.py` — tree-sitter TS/TSX + tsconfig path-alias resolver + shared tsserver LSP overlay | ~900 | ≥ 40 | TS/TSX fixture suite + ≥ 85% tree-sitter-only + ≥ 95% with tsserver + path-alias resolution test | I.4, I.5 |
| **I.7** | `graph_os/extractors/code_shell.py` + `code_yaml.py` + `graph_os/extractors/contracts.py` — shell `source` chain + YAML cross-refs + contract detector incl. DRF `router.register`, Next.js dynamic segments, FastAPI `include_router`, gRPC `.proto`, Celery / RQ / Channels handlers (§9.11) | ~700 | ≥ 35 | full coding-os hook graph visible + `cos-env.sh` inbound edges ≥ 30 + all 21 MCP tools detected + **external fixture suite** (django-rest + fastapi + nextjs app, each with ≥ 5 dynamic routes, detection rate ≥ 80%) | I.4 |
| **I.8** | All **11** `cos_graph_*` MCP tools in `graph_os/tools/graph.py` — `_query`, `_context`, `_impact`, `_detect_changes`, `_trace`, `_similar`, `_references`, `_path`, `_export`, **`_rename_plan`**, **`_contracts`**. Retire legacy `cos_graph` as shim. **Storage audit:** DB ≤ 200MB on 10k-file dogfood. | ~1100 | ≥ 44 (≥ 4 per tool × 11) | per-tool tests (happy path + envelope + token budget + 1 edge case each, Rule 14) + dogfood in AGENTS.md | I.2, I.3, I.4, I.6, I.7 |
| **I.9** | `core/thinking_os/orchestrator/` — full implementation (registry, dispatcher, worker_pool, progress, roles/indexer_graph_os.py, roles/lsp_warm_start.py, roles/migrator_embeddings.py) | ~850 | ≥ 20 | parallel indexing 10k files < 60s + cancellation + crash-restart + role-isolation (one crashing role does not block others) | I.4 |
| **I.10** | `graph_os/viewer/` — **Sigma.js + Graphology + ForceAtlas2** WebGL viewer + `cos graph-viz` CLI + Windows fallback + Windows CI matrix + `--bundled` offline mode + **CSP nonce** (§15.1.1) | ~700 | ≥ 15 | 10k-node sample FPS ≥ 30 + a11y fallback list-view + export JSON round-trip + CI green mac/linux/windows + **CSP auditor** + **XSS fuzz** + **nonce uniqueness** | I.8 |
| **I.11** | **Ingestion flexibility:** `graph_os/ingest/local.py`, `ingest/github.py`, `ingest/zip.py` + `cos graph-index-github`, `cos graph-index-zip` CLI + **size / file / timeout guards** (`--max-size`, `--max-files`, `--timeout`, `--shallow`) | ~400 | ≥ 15 | e2e clone + index + **refuse clone > `--max-size`** + **refuse ZIP bomb** + cached clones under `~/.coding-os/remote-repos/` | I.8 |
| **I.12** | **Repo groups:** `graph_os/groups/` module + group-level Kùzu DB at `~/.coding-os/groups/<name>/` + cross-repo edge detection (HTTP contract, MCP, gRPC, config) + **`group-membership.yaml` ownership declaration** (§17.3) + `cos graph-group` subcommands + `group` param across all MCP tools | ~750 | ≥ 18 | 3-repo fixture: inferred confidence 0.6; ownership-declared 0.95 + conflicting-ownership test (sync fails cleanly) + `cos_graph_contracts(group=…)` returns union + doctor C19 green | I.8, I.11 |
| **I.13** | Scale benchmark suite (1k / 10k / 100k / 500k / 1M symbol fixtures) + perf regression gate + **publish measured numbers** to `docs/benchmarks/graph-os.md` (commit SHA + hardware) | ~450 | ≥ 10 | Kùzu < 1s P95 at 500k OR §8.5 extrapolations replaced by measured SLO + SQLite fallback < 3s P95 at 100k + regression gate fails PR > 20% worse | I.8, I.9 |
| **I.14** | `graph-explorer` skill + `codebase-explorer` update + AGENTS.md / CLAUDE.md sections ("Graph Queries", "Rename Workflow", "Contracts Audit") + `cos doctor` C16 / C17 / C18 / C19 / C20 / C21 / C22 + `enforce-graph-context.sh` + `enforce-rename-plan.sh` hooks + `docs/engineering/graph-os-queries.md` + `docs/benchmarks/graph-os.md` finalization | ~150 code + docs | ≥ 8 | docs-lint green + skill-enforcement tests + hooks fire on dogfood edit + dogfood-rename workflow + markdown link check passes | all above |

**Aggregate test floor:** 40 + 25 + 30 + 20 + 50 + 25 + 40 + 35 + 44 + 20 + 15 + 15 + 18 + 10 + 8 = **≥ 395 new tests** across Phase I. Target total when Phase I ships: 1083 baseline + 395 = **≥ 1478 tests passing** — supersedes the earlier "1200+" hand-wave.

**Parallelization plan (per formula-9 principle):**
- I.0 must ship first (backends + protocol).
- I.1 (BGE-M3 migration) runs in parallel with I.2 + I.3 (extractors that don't depend on embeddings yet).
- I.4 (Python extractor) unlocks I.5 (Python LSP) and I.6 (TS/TSX + LSP).
- I.7 (shell + yaml + contracts) runs in parallel with I.4/I.5/I.6.
- I.8 (11 MCP tools) waits on all extractors.
- I.9 (orchestrator) can start after I.4 — uses Python extractor as its first payload.
- I.10 (Sigma.js viewer) + I.11 (ingestion) + I.13 (benchmarks) can run in parallel after I.8.
- I.12 (groups) needs I.8 + I.11 (needs ingestion for `add` command on remote repos).
- I.14 (docs + skill + doctor + hooks) is the finalizer.

**Minimum viable ship point:** After I.3 the agent can query a graph of docs + tasks (no code yet) via MCP. After I.6 the full multi-language code graph is live with LSP precision ≥95%. After I.8 all 11 MCP tools work, including `_rename_plan` + `_contracts`. Everything else is ergonomics + scale.

---

## 20. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **R-I-1: Graph density explosion** (e.g., `db.py` has 400 inbound import edges) | Viewer lag; MCP tools return huge payloads | Sigma.js WebGL renders 10k+ nodes; `cos_graph_*` has `limit` + `confidence_min`; edge pruning by `edge_type` filter |
| **R-I-2: Tree-sitter resolution false positives** | Wrong `calls` edges mislead the agent | Evidence-weighted confidence; agent uses `confidence_min=0.6` by default; LSP escalation raises ceiling ≥95% |
| **R-I-3: Broken links accumulate** | Viewer clutter, stale edges | `.graph-broken-links.log` SSOT; `cos doctor` check C16; weight=0.5 so they rank last |
| **R-I-4: Large-repo backfill latency** | Initial `cos graph-reindex` takes >1hr on 500k-file monorepo | I.13 benchmark + Kùzu backend; parallel indexer via orchestrator |
| **R-I-5: Schema migration breaks existing DBs** | Users on v11 lose data | Migration v12 is append-only (Rule 10); `has_graph_nodes_table()` + `has_graph_edges_table()` + `has_graph_evidence_table()` helpers; v12 round-trip test required in I.0; `block-migration-conflict.sh` catches accidental version collision |
| **R-I-6: Incremental cascade goes unbounded** | Single edit re-parses 10k files | Cascade bounded by import-graph reachability + hard cap of 500 files per edit; fallback to "mark stale, full reindex later" |
| **R-I-7: LSP subprocess hangs** | Agent session blocks on pyright crash | LSP adapter has 5s timeout + circuit breaker; fallback to tree-sitter silently |
| **R-I-8: Multi-repo confusion** | Cross-repo edges leak into wrong DB | Repo registration explicit; group DB isolated at `~/.coding-os/groups/<name>/`; `cos_graph_*` `repo` OR `group` param required for cross-repo queries |
| **R-I-9: Viewer security** (embedded JSON XSS + CDN supply-chain) | User opens malicious repo in viewer; CDN compromise | Escape all labels/signatures; CSP header in the HTML; SRI integrity hashes on all CDN scripts; `--bundled` mode for air-gapped |
| **R-I-10: Dynamic import blind spots** | Misleading "no references found" | `graph-explorer` skill warns on `importlib`/`require(expr)` patterns; confidence of call edges labeled `dynamic_possible=true`; `_rename_plan` `check_strings=true` catches string-literal dispatch |
| **R-I-11: Token budget overruns** | Agent context filled with graph output | Hard per-tool caps + `next_step_hint` + `cursor` pagination |
| **R-I-12: Rename plan misses non-obvious sites** | Agent renames half-way, breaks prod | `_rename_plan` combines graph walk + string-literal grep + comment scan; always returns `risk` + `suggested_order`; `enforce-rename-plan.sh` hook blocks rename edits without a prior `_rename_plan` call |
| **R-I-13: Cross-repo contract inference false positives** | Frontend `fetch('/api/users')` incorrectly mapped to backend route when two backends share a path | Group edge confidence capped at 0.8; group members can declare explicit ownership in `.coding-os/group-membership.yaml` to disambiguate |
| **R-I-14: GitHub ingestion — private repos & secrets** | User clones a repo with secrets into shared cache | `cos graph-index-github` refuses private repos without explicit `--auth` flag; clones to `~/.coding-os/remote-repos/` with `.gitignore`-respecting indexer; never transmits code anywhere |
| **R-I-15: Sigma.js FPS regression at high node count** | Viewer becomes sluggish around 30k+ nodes | Level-of-detail: hide labels past zoom threshold; cluster nodes at low zoom; progressive rendering; benchmark in I.10 ship gate |

---

## 21. Ship Checklist (per slice)

Each slice's DoD:
- [ ] Code + tests in `core/graph-os/` (follow Rule 13 function-header convention)
- [ ] Envelope compliance (Rule 14): every tool returns `ok(data)` or `fail(...)` via `@safe_tool`
- [ ] `make verify` green
- [ ] `uv run pytest core/graph-os/tests/ -q` green
- [ ] MCP self-test: `python core/thinking_os/server.py --test` lists the new tool(s)
- [ ] Docs-lint: AGENTS.md / CLAUDE.md updated if the slice is user-facing
- [ ] Hook regression: `cos hooks-log` shows expected entries after a dogfood Write/Edit
- [ ] No hardcoded stack/adapter literals (Rule 12)
- [ ] Scale check: for extractor slices, benchmark on `coding-os` itself

Phase I done when:
- [ ] All 15 slices (I.0 – I.14) shipped
- [ ] Agent can answer *"what breaks if I change X?"* in <500ms on `coding-os`
- [ ] Agent produces a complete rename plan via `_rename_plan` before any refactor
- [ ] `cos_graph_contracts` lists all 21 MCP tools in the `coding-os` repo
- [ ] `cos graph-viz` opens a browser with a WebGL graph (Sigma.js, 10k+ nodes smooth)
- [ ] `cos graph-index-github <public_url>` works end-to-end
- [ ] `cos graph-group sync` produces cross-repo contract edges on the 3-repo fixture
- [ ] Dogfood: the graph contains every hook, every MCP tool, every skill, every rule, every task, with correct cross-layer edges
- [ ] 1200+ tests passing (current 1083 + ~120 for graph-os)
- [ ] `cos doctor` checks C16, C17, C18, C19 all green
- [ ] AGENTS.md / CLAUDE.md updated with "Graph Queries", "Rename Workflow", "Contracts Audit" sections

---

## 22. Design Decisions (finalized 2026-04-19, reviewed & expanded post-graph-tool/gitreverse study)

All twelve open questions are resolved:

1. **Embedding model** — ✅ **BGE-M3** replaces MiniLM-L6-v2.
   - Reason: multilingual (Persian docs index correctly), 1024-dim dense+sparse+multi-vector, state-of-art on MTEB and CoIR 2026, Apache 2.0.
   - Cost: ~560MB model download, 2.7× embedding storage vs MiniLM. Acceptable for enterprise-grade product.
   - One-time migration script re-embeds `doc_chunks` on first run.

2. **Graph backend** — ✅ **Kùzu as primary**, SQLite as fallback.
   - Reason: 10-100× faster graph walks, native Cypher + HNSW vectors, embedded (single file like SQLite), Apache 2.0.
   - Fallback path kept for constrained environments; selected automatically if Kùzu binary unavailable.
   - Full parity tests in I.0 (both backends return identical results for 50 scenarios).

3. **Heading-scoped doc edges** — ✅ **Both** — `links_to` at file level, `cites_heading` at heading level. Agents pick the right one by edge_type.

4. **Confidence threshold** — ✅ Default `confidence_min=0.3` for all `cos_graph_*` tools; agent-overridable per call. Edges below 0.3 persist in DB but are pruned from agent responses by default. Viewer renders them as dashed red lines.

5. **Orchestrator** — ✅ **Fully implemented in Phase I** (not stub). Real dispatcher + worker pool + registry + parallel dispatch + cancellation + progress metrics.

6. **Windows** — ✅ Full cross-platform CI matrix (macOS + Linux + Windows). Viewer falls back to printing the file path if `webbrowser.open` returns False.

7. **`cos update` vs user data** — ✅ Clarified. `cos update` only updates framework files (`core/**`, `adapters/**`, `templates/**`). User data (`.coding-os/thinking-os.db`, `.coding-os/graph-os.kuzu`, `.coding-os/<agent>/`) is **never** touched. Schema migrations are append-only (Rule 10) and run on MCP server startup — user's existing data is preserved across all schema upgrades.

8. **LSP overlay** — ✅ Default ON (not opt-in). pyright + tsserver as long-lived subprocesses, reused across files. Circuit breaker on crash. Target precision ≥95% with LSP (vs ≥85% tree-sitter-only).

9. **Viewer rendering stack** — ✅ **Sigma.js (WebGL) + Graphology + ForceAtlas2 worker** replaces D3. Same stack as graph-tool — proven at industrial scale. Handles 10k+ nodes smoothly; D3/SVG chokes past 1k. SRI-hashed CDN dependencies + `--bundled` offline mode.

10. **Rename workflow** — ✅ New MCP tool `cos_graph_rename_plan(uid, new_name)` ships in I.8. Combines graph walk + string-literal grep + comment scan + config file scan. Enforced by `enforce-rename-plan.sh` PreToolUse hook on multi-file rename operations.

11. **Service contracts** — ✅ New MCP tool `cos_graph_contracts(scope, kinds)` ships in I.8. Detects HTTP routes, MCP tools, gRPC, event handlers, websockets across Python/TS/Go. Dedicated extractor `graph_os/extractors/contracts.py` in I.7.

12. **Repo groups & cross-repo queries** — ✅ Full `cos graph-group` subcommand suite + group-level Kùzu DB + cross-repo edge detection (HTTP contract, MCP, gRPC, config) ships in I.12. `group` param on all `cos_graph_*` tools. GitHub/ZIP ingestion in I.11 enables groups to include remote repos. Ownership declaration (§17.3) disambiguates overlapping routes.

13. **Migration version** — ✅ Target is **v12** (next append-only slot; live DB is at v11 as of 2026-04-19). Plan originally said v7; that was stale — `_migrate_v7_brain_hardening` and subsequent v8/v9/v10/v11 already exist. `block-migration-conflict.sh` enforces no collision.

14. **Embedding migration execution model** — ✅ Runs in a **dedicated background orchestrator role** (`migrator:embeddings`), not in MCP server startup. Checkpoint at `.coding-os/.embedding-migration.json`; resumable; crash-safe; dim-aware `cosine_similarity` prevents silent empty results (v12b adds `embedding_dim` column).

15. **Evidence storage** — ✅ **Normalized** into `graph_evidence_v12` (1:N off `graph_edges_v12`). Default MCP tool response does not include evidence; opt-in `include_evidence=True` joins at query time.

16. **LSP runtime topology** — ✅ **One** long-lived pyright + **one** long-lived tsserver, owned by the orchestrator, shared across indexer workers via Unix-domain socket. `lsp:warm-start` role runs before workers to absorb cold-start cost once.

17. **Backend failure policy** — ✅ **Fail loud, not silent.** If Kùzu is configured but offline, tools return `fail("unavailable", …, retryable=true)` rather than silently serving a 10× slower SQLite result.

18. **Determinism & pinning** — ✅ Tree-sitter + grammars + Kùzu + BGE-M3 tokenizer pinned in `pyproject.toml::optional-dependencies.graph-os`; I.0 golden test asserts byte-identical re-indexing.

19. **Plan review action items** — ✅ Tracked in §25 below, each with owner slice and status.

---

## 23. Deprecation & Backwards Compatibility

### 23.1 Legacy `cos_graph` tool

The existing `cos_graph` tool (migration v4, `co_edit` + `concept_link` edges only) is replaced by the eleven `cos_graph_*` tools shipped in I.8. Transition timeline:

| Window | State of `cos_graph` | User impact |
|---|---|---|
| Pre-I.8 | Operational as today | none |
| I.8 | Thin shim forwarding to `cos_graph_context` with `edge_types=['co_edit', 'concept_link']`. Logs `deprecated_tool=cos_graph` to `cos_metric_record`. | none (behavior preserved) |
| I.9 | Shim emits a warning message in envelope: `meta.deprecated=true; sunset=<date+180d>` | callers see a warning but results still flow |
| I.14 (or next major version after) | Shim removed; tool returns `fail("not_found", "cos_graph retired; use cos_graph_context(edge_types=['co_edit'])")` | consumers must migrate |

Two releases (≥ 180 days) of warning before removal. `cos doctor` check C23 surfaces any call site still using the legacy name so the migration is visible to operators.

### 23.2 `concept_graph` table

Retains its v4 shape. The legacy writer ([core/thinking_os/graph.py](../core/thinking_os/graph.py)) keeps writing `co_edit` edges there for backward compatibility with pre-I.8 consumers. The I.8 shim reads from `concept_graph` AND `graph_edges_v12` and unions the result — no data migration required. A one-shot backfill (`cos graph-backfill-concept-graph`) is provided for operators who want a single source of truth but it is **not run automatically**.

### 23.3 Hook contract (`auto-reindex-docs.sh`)

Extended in-place (not renamed) to call both `doc_indexer` and the new graph-os extractors. Behavior under v11 DB (graph-os tables absent) is explicit no-op on the graph path, identical to pre-I.0 behavior — consumers on an older schema see no regression.

### 23.4 `.coding-os/rag-config.yaml` schema

I.0 introduces a top-level `graph:` block. Existing installations without this block get defaults as if `backend: auto`, `lsp.enabled: true`, `cascade_max_files: 500`, `enforce_context_on: []`. The CLI's `cos setup` command writes an annotated default block on `cos update`, never overwriting user edits.

---

## 24. Determinism & Test Discipline (cross-slice)

### 24.1 Pinned dependencies

The `graph-os` extra in `pyproject.toml` must pin:

```toml
[project.optional-dependencies]
graph-os = [
    "sentence-transformers==2.7.0",     # BGE-M3 host
    "numpy>=1.24.0,<3.0.0",
    "tree-sitter==0.22.0",
    "tree-sitter-python==0.21.0",
    "tree-sitter-typescript==0.21.0",
    "tree-sitter-bash==0.21.0",
    "tree-sitter-yaml==0.6.1",
    "kuzu==0.7.1",
]
```

Version ranges are deliberately tight because grammar upgrades can change AST shape → change `uid`s → cascade-invalidate the entire graph. Upgrades are their own slice (Phase J) with a `make graph-rebaseline` command that captures a new golden set before unpinning.

### 24.2 Golden reproducibility

I.0 ships `tests/test_graph_determinism.py`:
1. Fixture: a 50-file Python project in `tests/golden/graph-os/fixture/`.
2. Run `graph-reindex` three times with a clean DB each time.
3. Assert: all `graph_nodes` rows and `graph_edges_v12` rows are byte-identical across runs (stable `uid`, stable `source_span`, stable `confidence`).
4. Any grammar / Kùzu / BGE-M3 version bump that breaks this test must update the golden set in the same PR.

### 24.3 Test pyramid per slice

- **Unit:** AST pattern extractors, symbol-table lookup, edge-type-specific helpers.
- **Integration:** extractor + DB round-trip; hook + re-index cascade.
- **Parity:** SQLite backend vs Kùzu backend returning the same result (§12.6).
- **Scale benchmark:** per `I.13` but spot-checked in I.4, I.6, I.8 ship gates.
- **Dogfood:** `coding-os` itself indexed and queried as the first consumer of every tool.

### 24.4 Aggregate target

≥ **395 new tests** across I.0 – I.14 (§19). Phase I done state: **≥ 1478 tests passing** (baseline 1083 at commit-SHA dated 2026-04-19 + 395 new).

---

## 25. Review Action Items (tracked before implementation starts)

Living checklist — each item resolves a concrete issue raised during the 2026-04-19 plan review. When all are green, the plan is ready to execute.

| # | Severity | Item | Owner slice | Status |
|---|---|---|---|---|
| 1 | P0 | `embedding_dim` column on legacy `embeddings`; `cosine_similarity` routes by dim (no silent `[]`) | I.0 + I.1 | ✅ written into plan |
| 2 | P0 | Parity matrix ≥ 189 scenarios; fail-loud backend fallback | I.0 | ✅ §12.6 |
| 3 | P0 | Embedding migration runs as `migrator:embeddings` background role; non-blocking startup | I.1 + I.9 | ✅ §6 Stage 6 |
| 4 | P1 | Formula mapping covers **F1–F11** (adds F1 / F4 / F9) | I.14 docs | ✅ §14 |
| 5 | P1 | Shared LSP subprocess + `lsp:warm-start` role + per-phase latency budgets | I.5 + I.9 | ✅ §7.4 |
| 6 | P1 | Cross-repo confidence 0.6 inferred / 0.95 declared + `group-membership.yaml` | I.12 | ✅ §17.3 |
| 7 | P1 | Per-slice minimum test count; ≥ 395 aggregate | all | ✅ §19 |
| 8 | P1 | Incremental `<200ms` SLA: sync budget 200ms; LSP fire-and-forget; `cos_graph_wait_lsp` opt-in | I.5 + I.8 | ✅ §8.2 |
| 9 | P1 | Contracts detector covers DRF `router.register`, Next.js dynamic segments, FastAPI `include_router` | I.7 | ✅ §9.11 |
| 10 | P2 | Pinned tree-sitter / Kùzu / BGE-M3 versions; determinism golden test | I.0 | ✅ §24 + P-I-11 |
| 11 | P2 | Evidence JSON normalized into `graph_evidence_v12`; on-demand fetch | I.0 + I.8 | ✅ §5.3 |
| 12 | P2 | Viewer CSP nonce + JSON-in-block + XSS fuzz test; `--bundled` inherits nonce | I.10 | ✅ §15.1.1 |
| 13 | P2 | `cos graph-index-github` size/file/timeout guards; ZIP-bomb refusal | I.11 | ✅ §19 I.11 |
| 14 | P2 | Cascade limits (`cascade_max_files`, `cascade_max_depth`) + background full-resolve overflow | I.8 | ✅ §8.3 |
| 15 | P2 | I.13 publishes **measured** benchmarks (not extrapolations) | I.13 | ✅ §8.5 + §19 |
| 16 | P3 | `docs/engineering/graph-os-queries.md` guide | I.14 | ⏳ ship gate |
| 17 | P3 | Remove `/tmp/graph-tool` local path; cite public source | plan edit | ⏳ §4 edit |
| 18 | P3 | `enforce-graph-context.sh` reads scope list from `rag-config.yaml` | I.14 | ✅ §11.2 |
| 19 | P3 | Baseline dated: 1083 tests at `main@2026-04-19` | plan + benchmarks doc | ✅ P-I-10 + §24.4 |
| 20 | P3 | TechSpec template will get an "Observability Budget" section post-I.14 | post-I.14 | ⚠ out-of-scope (not blocking) |
| 21 | P3 | `docs/engineering/mcp-error-envelope.md` existence verified | pre-I.0 | ✅ file present |
| 22 | P3 | §23 deprecation timeline for `cos_graph` tool + `concept_graph` table | plan | ✅ §23 |
| 23 | P0 (new) | Migration version v7 collision — actual DB is v11, plan now targets v12 | I.0 | ✅ throughout |

Legend: ✅ = addressed in this plan ∙ ⏳ = deliverable of a named slice ∙ ⚠ = flagged as out-of-Phase-I scope.

---

## 26. Why `graph-os` is the Right Name

- Parallel to `thinking-os`. Two cognitive subsystems. Easy to reason about.
- Short (7 chars) — readable in logs, env vars, CLI output.
- Not language-specific, not stack-specific — just "operating system for graphs".
- Reserves a clear namespace: `core/graph-os/`, `graph_os.*` in Python, `cos_graph_*` for MCP tools, `graph:` prefix in node kinds.
- Matches industry convention (Sourcegraph, Code Search, Code Graph) without being generic.

**Alternatives considered and rejected:**
- `coding-os-graph-knowledge` — verbose, breaks parallelism.
- `cos-graph` — already a tool name (`cos_graph`); shadows.
- `knowledge-os` — too broad; knowledge ≠ graph.
- `graph-brain` — cute; unprofessional.

Decision: **`graph-os`**.
