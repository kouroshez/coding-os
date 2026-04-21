<!-- domain:DOCS | layer:reference | ssot:true | updated:2026-04-06 -->
# Phase B — RAG Integration: Execution Plan

> Nav: [Development Roadmap](./development-roadmap.md) | [Architecture](./architecture.md)

Purpose: Detailed, implementation-ready plan for Phase B (RAG / Document Knowledge Base).
Read when: Starting any Phase B sub-task or when the high-level plan in `~/.claude/plans/parsed-gathering-sun.md` needs project-internal context.
Skip when: Working on Phase A or Phase C tasks.
Read next: `core/thinking_os/db.py` (migration registration), `core/thinking_os/tools/memory.py` (search integration), `core/thinking_os/capture.py` (inline embedding hook).

## Status

- **Phase A — Template Completion:** ✅ DONE (38 new tests, 38 scaffold files, 9 governance docs, 6 stack-specific overlays per template, AGENTS.md placeholder substitution working end-to-end)
- **Phase B — RAG:** ⏳ THIS PLAN
- **Phase C — Hybrid Task Store:** 🔜 follows Phase B

## Why Now

Phase A delivered the complete docs hierarchy (PRD, architecture, ADRs, api-contracts, page specs, engineering rules, ops runbooks, design system). For a real-world project (NakoDigital reference: 430 markdown files, 17 MB), the agent cannot full-read all of these on every task. RAG provides selective retrieval — the agent gets only the chunks relevant to the active task instead of loading entire files.

Three concrete pain points Phase B solves:

1. **Semantic mismatch** in `cos_search`: agent searches "auth issue" but past pattern says "JWT token refresh failing" → no FTS5/LIKE match → agent re-discovers the same problem.
2. **Doc full-read cost**: agent working on `TASK-199 commission model` needs PRD §4.2, ADR-005, api-contracts/commerce.md, engineering/backend-rules.md § Money Handling. Without RAG: 5 full files (~5K tokens). With RAG: 4 relevant chunks (~600 tokens).
3. **No ranking on `learned_patterns`**: current `memory_search()` falls back to LIKE on patterns table (fixed relevance 0.6, no semantic ranking). Embeddings give true similarity ranking.

## Architecture

```
Layer 1: AGENT MEMORY (existing — augmented in Phase B)
   observations, learned_patterns, outcome_history
   Question: "Have I solved this before?"
   Tools: cos_search, cos_timeline, cos_details, cos_promote, cos_learn_*

Layer 2: DOCUMENT KNOWLEDGE BASE (NEW — Phase B core)
   document_chunks table (heading-aware chunks of docs/)
   Question: "What does the spec/rule/architecture say?"
   Tool: cos_doc_search (new)

Layer 3: TASK REGISTRY (Phase C)
   tasks table indexing docs/tasks/*.md
   Question: "What tasks are related? What dependencies?"

ALWAYS-ACTIVE (no RAG, full-read):
   AGENTS.md, CLAUDE.md, playbooks, governance/, current task detail
```

### What goes into RAG

| Source | Indexed? | Reason |
|---|---|---|
| `docs/PRD/**` | ✅ | Long, selective retrieval valuable |
| `docs/architecture/**` (incl. ADRs) | ✅ | Reference docs, large |
| `docs/api-contracts/**` | ✅ | Per-endpoint chunks useful |
| `docs/pages-content-spec/**` | ✅ | Per-page chunks (Next.js stack) |
| `docs/engineering/**` | ✅ | Coding rules, often selective |
| `docs/ops/**` | ✅ | Runbooks |
| `docs/design/**` | ✅ | Tokens, components |
| `docs/playbooks/**` | ❌ | Routing logic — must be holistic, full-read as skill |
| `docs/governance/**` | ❌ | Always-active rules |
| `docs/tasks/**` | ❌ | Phase C handles this with structured `tasks` table |
| `docs/00-index.md`, `foundation-map.md` | ❌ | Navigation hubs, full-read |
| `docs/workflow-docs/thinking-os-final-edition.md` | ⚠️ | Optional — large reference, opt-in via rag-config.yaml |

### What goes into the embeddings table (for memory search)

| Source | Embedded text | Purpose |
|---|---|---|
| `observations` | `title + narrative + concepts` | Augments FTS5 search with semantic match |
| `learned_patterns` | `pattern + concepts` | Replaces LIKE-only search with true similarity ranking |
| `outcome_history` | `narrative_key_insight + what_failed + what_worked` | Breakthrough narrative semantic retrieval |
| `document_chunks` | `heading_path + content` | Document RAG search (new) |

## Constraints & Decisions

- **Embedding model:** `sentence-transformers/all-MiniLM-L6-v2` (384 dims, ~22MB, ~5ms/embedding on CPU). User confirmed in plan-mode discussion.
- **Optional dependency:** `[project.optional-dependencies] rag = ["sentence-transformers>=2.2.0", "numpy>=1.24.0"]`. Core install stays lean.
- **No vector DB:** numpy brute-force cosine. Justified for <50K vectors (NakoDigital realistic load: ~9K).
- **Storage:** SQLite BLOB column with float32 bytes (1536 bytes per vector).
- **Graceful degradation:** every embedding call wrapped in try/except. If `sentence-transformers` not installed → fall back to existing FTS5/LIKE behavior. Same pattern as `has_fts5()` graceful degradation.
- **Migrations:** append-only. v5 = embeddings + document_chunks (single migration).
- **Inline embedding on capture:** fire-and-forget pattern. Never blocks the agent. Lazy model load on first call.

## Sub-Phase Breakdown

### B.1 — Foundation: embeddings module + migration v5

**Goal:** infrastructure ready, migration applied, basic tests pass.

**New file:** `core/thinking_os/embeddings.py`

```python
# Public API surface
def is_available() -> bool                                    # sentence-transformers importable?
def embed_text(text: str) -> bytes | None                     # 384-dim float32 (1536 bytes), or None
def embed_texts(texts: list[str]) -> list[bytes | None]       # batch
def cosine_similarity(query_vec: bytes, candidates: list[bytes]) -> list[float]
def upsert_embedding(conn, source_table: str, source_id: int, text: str) -> None
def search_similar(
    conn,
    query: str,
    source_tables: list[str] | None = None,
    limit: int = 5,
    threshold: float = 0.3,
) -> list[dict]                                                # [{source_table, source_id, score}]
def has_embeddings_data(conn) -> bool
def reindex_all(conn) -> dict                                  # bootstrap/upgrade
```

Design notes:
- Lazy model load via `@functools.lru_cache(maxsize=1)` on `_get_model()`.
- Text hash via `hashlib.sha256(text.encode()).hexdigest()[:16]` (reuse `capture._compute_content_hash` pattern).
- `embed_text` catches `ImportError` and returns `None`. All callers must handle `None`.
- `cosine_similarity` reads BLOBs once, computes via `numpy.dot(matrix, query_vec) / (norms * query_norm)` for vectorized speed.

**Modified:** `core/thinking_os/db.py`

Append migration v5 to the existing `MIGRATIONS` list (line 164 in db.py). Following the v2/v4 pattern:

```python
def _migrate_v5_rag(conn: sqlite3.Connection) -> None:
    conn.executescript("""
CREATE TABLE IF NOT EXISTS embeddings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_table TEXT NOT NULL,
    source_id    INTEGER NOT NULL,
    text_hash    TEXT NOT NULL,
    embedding    BLOB NOT NULL,
    model_name   TEXT DEFAULT 'all-MiniLM-L6-v2',
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_table, source_id)
);
CREATE INDEX IF NOT EXISTS idx_embeddings_source ON embeddings(source_table, source_id);

CREATE TABLE IF NOT EXISTS document_chunks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path  TEXT NOT NULL,
    source_type  TEXT NOT NULL,
    chunk_index  INTEGER NOT NULL,
    heading_path TEXT,
    content      TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    priority     REAL DEFAULT 0.5,
    mtime        INTEGER NOT NULL,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_path, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_path ON document_chunks(source_path);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_type ON document_chunks(source_type);
""")

MIGRATIONS.append((5, "Phase B: embeddings + document_chunks for RAG", _migrate_v5_rag))
```

Add `has_embeddings_table(conn)` (parallel to `has_fts5_table`).
Add `"embeddings"`, `"document_chunks"` to `_TABLES` list in `get_db_stats()`.

**Modified:** `pyproject.toml`

```toml
[project.optional-dependencies]
rag = ["sentence-transformers>=2.2.0", "numpy>=1.24.0"]
```

**New tests:** `core/thinking_os/tests/test_embeddings.py`

| Test | What it verifies |
|---|---|
| `test_is_available_when_installed` | When sentence-transformers in env → True |
| `test_is_available_when_missing` | Mock `ImportError` → False |
| `test_embed_text_returns_correct_size` | 1536 bytes (384 × float32) |
| `test_embed_text_graceful_degradation` | Returns None when model unavailable |
| `test_cosine_identical_vectors` | Score ≈ 1.0 |
| `test_cosine_orthogonal_vectors` | Score ≈ 0.0 |
| `test_upsert_embedding_inserts` | Row in DB after first call |
| `test_upsert_embedding_updates_on_text_change` | text_hash mismatch → re-embed |
| `test_upsert_embedding_skip_when_unchanged` | Same text → no DB write |
| `test_search_similar_finds_synonym` | "auth issue" finds "JWT token refresh" with score > 0.4 |
| `test_search_similar_respects_threshold` | Below threshold → excluded |
| `test_search_similar_filters_by_source_table` | Only requested tables returned |
| `test_reindex_all_populates_existing_records` | Bootstrap path |

**New tests:** `core/thinking_os/tests/test_db.py` additions
- `test_migration_v5_creates_embeddings_table`
- `test_migration_v5_creates_document_chunks_table`
- `test_migration_v5_idempotent`

**Verification (B.1):**
```bash
uv sync --extra rag
uv run --extra rag pytest core/thinking_os/tests/test_embeddings.py -v
uv run pytest core/thinking_os/tests/test_db.py -v   # without rag extras
```

### B.2 — Capture integration: inline embedding on write

**Goal:** every observation, pattern, and breakthrough narrative gets embedded automatically. Bootstrap-friendly.

**Modified files:**

1. `core/thinking_os/capture.py` — after `INSERT INTO observations` (around line 220), add:
   ```python
   try:
       from embeddings import upsert_embedding
       text_to_embed = f"{title} {narrative} {concepts_str}".strip()
       upsert_embedding(conn, "observations", obs_id, text_to_embed)
   except Exception:
       pass  # fire-and-forget — never break capture
   ```

2. `core/thinking_os/tools/learning.py`
   - In `_upsert_pattern()` (after row insert): embed `pattern + concepts`
   - In `learn_narrative()` (after `outcome_history` insert): embed `key_insight + what_failed + what_worked`

3. `core/thinking_os/session_enrich.py` — embed any new outcome_history entries created during enrichment.

**New Makefile target:**
```makefile
cos-reindex: ## Rebuild all embeddings (bootstrap or model upgrade)
	@uv run --extra rag python -m core.thinking-os.embeddings --reindex
```

Add `__main__` block to `embeddings.py` to support CLI invocation.

**New tests (additions to existing test files):**

| Test | File |
|---|---|
| `test_capture_observation_creates_embedding` | `test_capture.py` |
| `test_capture_observation_no_embedding_when_unavailable` | `test_capture.py` |
| `test_upsert_pattern_creates_embedding` | `test_learning.py` |
| `test_learn_narrative_creates_outcome_embedding` | `test_learning.py` |
| `test_reindex_all_picks_up_pre_existing_records` | `test_embeddings.py` |

**Verification (B.2):**
```bash
uv run --extra rag pytest core/thinking_os/tests/test_capture.py core/thinking_os/tests/test_learning.py -v
# Smoke test: simulate observation insert, verify embedding row created
uv run --extra rag python -c "
from core.thinking_os.capture import capture_observation
from core.thinking_os.db import init_db
import sqlite3
conn = init_db('/tmp/cos-test.db')
result = capture_observation({'tool_name': 'Edit', 'tool_input': {'file_path': 'app/auth.py'}})
print(result)
print(conn.execute('SELECT COUNT(*) FROM embeddings').fetchone())
"
```

### B.3 — Document indexer (new module)

**Goal:** `make docs-index` walks `docs/`, chunks markdown by heading, embeds each chunk, stores in `document_chunks` + `embeddings`.

**New module:** `core/thinking_os/doc_indexer.py`

```python
# Public API
def index_docs(
    conn,
    config_path: Path,
    project_root: Path,
    force: bool = False,
) -> dict:
    """Returns: {new: int, updated: int, deleted: int, total: int}"""

def chunk_markdown(
    content: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[dict]:
    """Returns: [{chunk_index, heading_path, content, content_hash}]
    Splits by H2 first, then H3 within each H2 if size exceeds chunk_size.
    Token estimate: ~4 chars per token (rough).
    """

def load_rag_config(config_path: Path) -> dict
def walk_sources(sources: list[dict], project_root: Path, exclude: list[str]) -> list[Path]

# CLI entry point
if __name__ == "__main__":
    # argparse: --config PATH --force --quiet
    ...
```

Chunking strategy:
- Split content at every `^## ` (H2). Each H2 becomes a candidate chunk.
- If an H2 chunk exceeds `chunk_size` (~500 tokens ≈ 2000 chars), split further at `^### ` (H3) inside it.
- If still too large, fall back to paragraph-based chunking with overlap.
- `heading_path` is built as `"<H1> > <H2> > <H3>"`.
- Front-matter HTML comment is stripped before chunking (it's metadata, not content).

mtime detection:
- For each source file, compare `os.stat(file).st_mtime` to the max `mtime` in `document_chunks` for that file.
- If file mtime ≤ stored mtime → skip.
- If file mtime > stored mtime → delete all chunks for that file, re-chunk, re-insert, re-embed.
- `--force` mode skips the mtime check.

**New scaffold:** `templates/_base/scaffold/.coding-os/rag-config.yaml`

```yaml
# RAG indexer configuration. Generated by `coding-os init`.
# Edit to add/remove indexed paths or tune chunking per source.

sources:
  - path: docs/PRD/
    type: prd
    chunk_size: 500
    chunk_overlap: 50
  - path: docs/architecture/
    type: architecture
    exclude: [adr/]
  - path: docs/architecture/adr/
    type: adr
    chunk_size: 1500   # ADRs are short — one chunk per ADR usually fits
  - path: docs/api-contracts/
    type: api_contract
  - path: docs/pages-content-spec/
    type: page_spec
  - path: docs/engineering/
    type: engineering
    priority: 0.7      # ranking boost — engineering rules often most actionable
  - path: docs/ops/
    type: ops
  - path: docs/design/
    type: design

exclude:
  - docs/playbooks/
  - docs/governance/
  - docs/tasks/
  - docs/00-index.md
  - docs/foundation-map.md
  - docs/feature-dependency-tree.md
  - docs/roadmap.md
  - docs/questions.md
  - docs/tasks.md
  - docs/workflow-docs/   # full-reference docs, opt-in
```

Add this file to `_overlay_scaffold()` in `cli/main.py` so it lands in the project on init.

**Modified:** `templates/_base/Makefile.base`

```makefile
docs-index: ## Index docs/ for RAG retrieval (incremental)
	@uv run --extra rag python -m core.thinking-os.doc_indexer --config .coding-os/rag-config.yaml

docs-reindex: ## Force full reindex (after model upgrade)
	@uv run --extra rag python -m core.thinking-os.doc_indexer --config .coding-os/rag-config.yaml --force
```

**New tests:** `core/thinking_os/tests/test_doc_indexer.py`

| Test | What it verifies |
|---|---|
| `test_chunk_by_h2` | A 3-section markdown produces 3 chunks |
| `test_chunk_h2_oversize_splits_at_h3` | H2 with content > chunk_size → split at H3 |
| `test_chunk_strips_front_matter` | HTML comment header not in chunk content |
| `test_heading_path_built_correctly` | `"H1 > H2 > H3"` format |
| `test_mtime_skip_unchanged` | File unchanged → 0 new chunks |
| `test_mtime_replace_changed` | File changed → old chunks deleted, new inserted |
| `test_force_reindex_replaces_all` | `--force` flag re-embeds everything |
| `test_index_respects_exclude_paths` | Excluded dirs not indexed |
| `test_index_respects_exclude_files` | Specific filenames not indexed |
| `test_priority_stored_per_source` | Source priority in `document_chunks.priority` |
| `test_index_against_real_nakodigital_subset` | Smoke test on a 5-file subset (no slow full index) |

**Verification (B.3):**
```bash
# Index a real-world subset
TMPDIR=$(mktemp -d /tmp/cos-doctest-XXXXXX)
uv run --directory ~/Files/Project/coding-os python -m cli.main init --agent claude --template django --project-dir "$TMPDIR"
cp /Users/ciro/Files/Project/NakoDigital/docs/PRD/0[1-5]*.md "$TMPDIR/docs/PRD/"
cd "$TMPDIR"
make docs-index
sqlite3 .coding-os/thinking-os.db "SELECT source_type, COUNT(*) FROM document_chunks GROUP BY source_type;"
# Expected: prd | <count>
```

### B.4 — New MCP tool: `cos_doc_search`

**Goal:** agent can query the document knowledge base directly.

**New module:** `core/thinking_os/tools/docs.py`

```python
def doc_search(
    conn,
    query: str,
    source_types: list[str] | None = None,
    limit: int = 5,
    dedupe_per_source: bool = True,
) -> list[dict]:
    """Returns:
       [{source_path, heading_path, content, score, source_type, mtime, priority}]

    Algorithm:
    1. Embed query via embeddings.embed_text(query).
    2. SELECT all (id, embedding, priority) from embeddings JOIN document_chunks
       WHERE source_table='document_chunks' [AND source_type IN (...)]
    3. cosine_similarity batch over all candidate embeddings.
    4. Final score = cosine * (0.7 + 0.3 * priority).
    5. Sort desc, take top (limit * 2).
    6. If dedupe_per_source: keep at most 2 chunks per source_path, then trim to limit.
    7. Return enriched results with metadata.
    """
```

**Modified:** `core/thinking_os/server.py`

Add new MCP tool:
```python
@mcp.tool(
    name="cos_doc_search",
    annotations={
        "title": "Search Project Documentation",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def cos_doc_search(
    query: str,
    source_types: str = "",
    limit: int = 5,
) -> str:
    """Semantic search over project documentation chunks.

    Use this when you need to find a specific spec, rule, or architecture
    decision. Returns chunks (300-500 tokens each) instead of full files.

    Args:
        query: Natural language search query (e.g. "commission rate calculation")
        source_types: Comma-separated filter (prd,architecture,adr,api_contract,page_spec,engineering,ops,design)
        limit: Max results (1-20, default 5)

    Returns:
        JSON with results [{source_path, heading_path, content, score, source_type}]
    """
    types = [t.strip() for t in source_types.split(",") if t.strip()] or None
    from tools.docs import doc_search
    results = doc_search(_db_conn, query=query, source_types=types, limit=limit)
    return json.dumps({"results": results, "count": len(results)}, indent=2, default=str)
```

Update `cos_health` to include `embeddings_count`, `document_chunks_count`, `embedding_model_available`.

**New tests:** `core/thinking_os/tests/test_doc_search.py`

| Test | What it verifies |
|---|---|
| `test_doc_search_returns_relevant_chunk` | Query "discount rules" finds chunk containing it |
| `test_doc_search_filter_by_source_type` | Only `prd` chunks returned when filter set |
| `test_doc_search_dedupe_per_source` | Same file produces ≤ 2 chunks in results |
| `test_doc_search_priority_boosts_engineering` | Engineering chunk outranks equal-similarity PRD chunk when priority differs |
| `test_doc_search_empty_when_no_index` | No chunks in DB → returns empty list cleanly |
| `test_doc_search_graceful_degradation` | Embeddings unavailable → returns empty + warning |

**Verification (B.4):**
```bash
# After indexing NakoDigital subset:
uv run --extra rag python -c "
from core.thinking_os.tools.docs import doc_search
from core.thinking_os.db import init_db
c = init_db('.coding-os/thinking-os.db')
import json
print(json.dumps(doc_search(c, 'commission rate', source_types=['prd', 'architecture'], limit=3), indent=2))
"
# Run via MCP self-test
uv run --extra rag python core/thinking_os/server.py --test
```

### B.5 — Existing tools: semantic augmentation

**Goal:** `cos_search`, `cos_learn_suggest`, `cos_route_skill` benefit from embeddings without breaking existing API.

**Modified:** `core/thinking_os/tools/memory.py`

In `memory_search()` (line 100), add a semantic branch alongside the existing FTS5/LIKE branches:

```python
# After existing FTS5/LIKE candidate gathering, before scoring:
semantic_hits = []
if has_embeddings_table(conn) and embeddings.is_available():
    try:
        semantic_hits = embeddings.search_similar(
            conn,
            query=query,
            source_tables=["observations", "learned_patterns", "outcome_history"],
            limit=limit * 3,
            threshold=0.3,
        )
    except Exception:
        semantic_hits = []  # never break existing search

# Merge semantic hits with FTS5/LIKE candidates by (source_table, source_id):
merged = {}
for c in candidates:
    key = (c["source_table"], c["id"])
    merged[key] = c
    merged[key]["semantic_score"] = 0.0
for h in semantic_hits:
    key = (h["source_table"], h["source_id"])
    if key in merged:
        merged[key]["semantic_score"] = h["score"]
    else:
        # Semantic-only hit — fetch the row, build a candidate dict
        row = _fetch_row(conn, h["source_table"], h["source_id"])
        if row:
            merged[key] = {**row, "fts_rank": 0.0, "semantic_score": h["score"]}

# Updated scoring: blend 5-signal with semantic
def _compute_blended_score(c):
    base = _compute_score(
        relevance=c.get("fts_rank") or 0.0,
        confidence=c.get("confidence") or 0.0,
        recency_days=c.get("recency_days") or 999,
        impact=c.get("impact_score") or 0.0,
        access_count=c.get("access_count") or 0,
    )
    semantic = c.get("semantic_score", 0.0)
    if semantic > 0.0:
        return 0.5 * semantic + 0.5 * base
    return base
```

**Modified:** `core/thinking_os/tools/learning.py`

Add `task_description: str = ""` parameter to `learn_suggest()`. When provided + embeddings available:
- Embed task_description
- Search outcome_history embeddings for top-3 semantically similar breakthroughs
- Merge with existing domain/complexity-filtered results (semantic results get a `reason: "semantic_breakthrough_match"` tag)

**Modified:** `core/thinking_os/tools/routing.py`

In `route_skill()`: when embeddings available + warm DB, also query for skills used in past tasks with semantically similar descriptions to the current one.

**Modified:** `core/thinking_os/server.py`
- `cos_search` — no signature change (memory_search handles it internally)
- `cos_learn_suggest` — add `task_description` arg, pass through
- `cos_health` — already updated in B.4

**New/modified tests:** `core/thinking_os/tests/test_memory.py`

Add `TestSemanticSearch` class:

| Test | What |
|---|---|
| `test_semantic_finds_synonym_observation` | "auth problem" finds an observation about "JWT refresh" |
| `test_semantic_falls_back_when_embeddings_missing` | No embeddings table → behaves like current memory_search |
| `test_blended_ranking_prefers_high_confidence_semantic_match` | Semantic match + confidence 0.9 outranks keyword-only match with confidence 0.5 |
| `test_semantic_only_hit_included` | An observation that matches semantically but has no FTS5 hit appears in results |
| `test_diversity_filter_still_applied_after_semantic_merge` | Same (memory_type, domain) deduped to 2 |

**Verification (B.5):**
```bash
uv run --extra rag pytest core/thinking_os/tests/test_memory.py -v
# Without RAG extras — confirm fallback
uv run pytest core/thinking_os/tests/test_memory.py -v
```

### B.6 — Polish & Documentation

- Add `cos-download-model` Makefile target to pre-download the model (avoids first-run latency)
- Stale embedding cleanup hook in `decay.py` (when text_hash mismatch detected during decay sweep)
- Update `core/docs/` and project `docs/architecture.md` with the three-layer retrieval description
- Update `docs/development-roadmap.md`: mark Phase B done, add B.6 polish items if any deferred
- Performance benchmark script: index NakoDigital docs/, time it, report chunks/sec and query latency

## Files Summary

| Type | Path |
|---|---|
| New module | `core/thinking_os/embeddings.py` |
| New module | `core/thinking_os/doc_indexer.py` |
| New module | `core/thinking_os/tools/docs.py` |
| New scaffold | `templates/_base/scaffold/.coding-os/rag-config.yaml` |
| Modified | `core/thinking_os/db.py` (migration v5, `_TABLES`, `has_embeddings_table`) |
| Modified | `core/thinking_os/capture.py` (inline embedding) |
| Modified | `core/thinking_os/tools/learning.py` (`_upsert_pattern`, `learn_narrative`, `learn_suggest`) |
| Modified | `core/thinking_os/tools/memory.py` (`memory_search` blended scoring) |
| Modified | `core/thinking_os/tools/routing.py` (`route_skill` semantic augment) |
| Modified | `core/thinking_os/session_enrich.py` (embedding for new outcome_history) |
| Modified | `core/thinking_os/server.py` (new `cos_doc_search`, updated `cos_health`, `cos_learn_suggest` signature) |
| Modified | `pyproject.toml` (rag optional dep group) |
| Modified | `templates/_base/Makefile.base` (`docs-index`, `docs-reindex`, `cos-reindex`) |
| Modified | `cli/main.py` (rag-config.yaml in scaffold overlay) |
| New tests | `core/thinking_os/tests/test_embeddings.py` |
| New tests | `core/thinking_os/tests/test_doc_indexer.py` |
| New tests | `core/thinking_os/tests/test_doc_search.py` |
| Modified tests | `test_capture.py`, `test_learning.py`, `test_memory.py`, `test_db.py` |

**Total: 3 new modules, 1 new scaffold file, 11 modifications, 3 new test files, 4 test additions.**

## Existing Code to Reuse

| Pattern | Where it lives | Reuse for |
|---|---|---|
| FTS5 graceful degradation | `db.py:has_fts5()`, `memory.py:use_fts5` branch | Same pattern for `has_embeddings_data()` and `embeddings.is_available()` |
| Content hash dedup (16-char SHA256) | `capture.py:_compute_content_hash()` | Same for `embeddings` text_hash and `document_chunks` content_hash |
| Fire-and-forget try/except | `capture.py`, `session_enrich.py` | All embedding write paths |
| 5-signal scoring | `memory.py:_compute_score()` | Extended with semantic signal in `_compute_blended_score()` |
| Migration append pattern | `db.py:MIGRATIONS.append(...)` | Add `(5, ..., _migrate_v5_rag)` |
| Lazy import pattern | `compress.py` (anthropic SDK try/except) | Same for sentence-transformers in `embeddings.py` |
| CLI overlay scaffold | `cli/main.py:_overlay_scaffold()` | Drops `rag-config.yaml` into project |
| Test fixtures | `tests/test_template_scaffold.py:_init_project()` | Reusable for end-to-end RAG smoke tests |

## Open Decisions (deferred to implementation time)

1. **Should `cos_doc_search` accept `min_score` parameter?** Recommendation: yes, default 0.3, lets agents tighten precision.
2. **Should `embed_texts` parallelize with `concurrent.futures`?** Recommendation: no, sentence-transformers `model.encode(list)` already batches efficiently.
3. **Should we cache the embedding model in a separate process?** Recommendation: no for v0.2, MCP server stays in memory across calls so lazy load is enough.
4. **Should we expose a `cos_doc_indexed_status` MCP tool?** Recommendation: yes — small addition that lets agents check if a path is indexed before searching.
5. **How to handle very large markdown files (>50KB)?** Recommendation: chunking already handles this naturally via H2/H3 splitting; no special-case needed.

## Verification Matrix (Phase B Complete)

```bash
# 1. Migration v5 applied cleanly
uv run python -c "from core.thinking_os.db import init_db; c=init_db(); tables = {r[0] for r in c.execute('SELECT name FROM sqlite_master').fetchall()}; assert 'embeddings' in tables and 'document_chunks' in tables; print('OK')"

# 2. All embedding tests pass (with RAG extras)
uv run --extra rag pytest core/thinking_os/tests/test_embeddings.py core/thinking_os/tests/test_doc_indexer.py core/thinking_os/tests/test_doc_search.py -v

# 3. Existing tests still pass with RAG enabled
uv run --extra rag pytest core/thinking_os/tests/ tests/ -v

# 4. Existing tests still pass WITHOUT RAG extras (graceful degradation)
uv run pytest core/thinking_os/tests/ tests/ -v

# 5. End-to-end smoke test on NakoDigital subset
TMPDIR=$(mktemp -d /tmp/cos-rag-test-XXXXXX)
uv run --directory ~/Files/Project/coding-os python -m cli.main init --agent claude --template django --project-dir "$TMPDIR"
cp /Users/ciro/Files/Project/NakoDigital/docs/PRD/*.md "$TMPDIR/docs/PRD/" 2>/dev/null || true
cp /Users/ciro/Files/Project/NakoDigital/docs/architecture/0[12]*.md "$TMPDIR/docs/architecture/" 2>/dev/null || true
cd "$TMPDIR"
make docs-index
sqlite3 .coding-os/thinking-os.db "SELECT source_type, COUNT(*) FROM document_chunks GROUP BY source_type;"
# Expected: prd | N, architecture | M (where N+M > 0)

# 6. cos_doc_search returns results
uv run --extra rag python -c "
import json, sys
sys.path.insert(0, '/Users/ciro/Files/Project/coding-os/core/thinking_os')
from db import init_db
from tools.docs import doc_search
c = init_db('.coding-os/thinking-os.db')
print(json.dumps(doc_search(c, 'commission', limit=3), indent=2))
"

# 7. MCP server self-test
uv run --extra rag python /Users/ciro/Files/Project/coding-os/core/thinking_os/server.py --test
```

## Risk & Mitigation

| Risk | Likelihood | Mitigation |
|---|---|---|
| sentence-transformers download fails on first run (network/firewall) | Medium | Document `cos-download-model` target. Document offline install path. |
| numpy cosine slow at >50K vectors | Low (NakoDigital ~9K) | Phase 5 (deferred): swap to `hnswlib` or `sqlite-vss` if real users hit this |
| Markdown chunking misses heading-less docs | Medium | Fall back to paragraph chunking with overlap |
| Inline embedding adds latency to capture path | Low (~5ms) | Already fire-and-forget; never blocks |
| Embedding model upgrade breaks old vectors | Medium | `model_name` column lets us detect mismatch; `cos-reindex` rebuilds |
| `learned_patterns` LIKE fallback path divergence | Low | Test both paths explicitly: with embeddings on AND off |
| Stale embeddings on file rename/delete | Medium | mtime + content_hash detection; orphan cleanup in B.6 |

## Recommended Execution Order

1. **B.1** — Foundation (embeddings.py + migration v5 + tests). One commit.
2. **B.2** — Capture integration (inline embedding hooks). One commit.
3. **B.3** — Document indexer (chunking + indexer + rag-config.yaml). One commit.
4. **B.4** — `cos_doc_search` MCP tool. One commit.
5. **B.5** — Existing tool augmentation (memory.py blended scoring + learning.py task_description). One commit.
6. **B.6** — Polish, docs update, performance bench. Final commit.

Each sub-phase is independently shippable and testable. After each, run the verification matrix's relevant subset before moving on.

## Estimated Scope

- ~600 lines of new Python (embeddings.py: ~200, doc_indexer.py: ~250, tools/docs.py: ~150)
- ~400 lines of test code (test_embeddings.py: ~200, test_doc_indexer.py: ~150, test_doc_search.py: ~100, plus additions)
- ~100 lines of modifications across existing files
- 1 new scaffold file (rag-config.yaml ~30 lines)
- 1 new MCP tool

**Phase A delivered 38 tests, 38 scaffold files, ~500 lines of CLI/script logic.** Phase B is similar in scope: heavier on new module code, lighter on scaffold.
