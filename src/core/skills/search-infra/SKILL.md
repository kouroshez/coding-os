---
name: search-infra
description: Design and operate full-text and vector search infrastructure — inverted-index engines (Elasticsearch/OpenSearch, Meilisearch, Typesense), analyzers and tokenization, relevance tuning (BM25, boosting, synonyms), faceting, and semantic/vector search (embeddings, ANN indexes, hybrid retrieval). Use when adding a search box, choosing a search engine, designing an index mapping and analyzer chain, tuning relevance, building autocomplete, deciding keyword vs vector vs hybrid retrieval, or keeping a search index in sync with the source database. Boundary vs db-design — db-design owns the durable transactional source of truth (normalized PostgreSQL schema, known-key indexes, migrations, ACID); this skill owns the derived denormalized search index built FROM that source for ranked free-text/semantic retrieval, where the engine is eventually-consistent, rebuildable, and never the system of record. Defers cache concerns to redis and RAG prompt assembly to llm-patterns.
tier: architecture
domain: [data, backend]
last_reviewed: "2026-06-14"
---

# Search Infrastructure — Ranked Retrieval Done Right

A practical guide to building search that returns the *relevant* result, not just a matching row. Covers classic full-text (inverted index, BM25) and modern semantic (embeddings, vector ANN) retrieval, and the index-sync discipline that keeps either honest. Stack-agnostic; recipes target Elasticsearch/OpenSearch, Meilisearch, Typesense, and pgvector/Qdrant as the reference engines.

## When to Use This Skill

- Adding a search box, autocomplete, or "find similar" to a product.
- Choosing a search engine — managed Elastic vs Meilisearch vs Typesense vs Postgres FTS vs a vector DB.
- Designing an index mapping: which fields are searchable, which are filters, which analyzer.
- Tuning relevance — results are "technically matching but useless", boosting, synonyms, typo tolerance.
- Deciding keyword vs vector vs hybrid retrieval for a given query distribution.
- Keeping the search index consistent with the database that owns the data.

Skip when: the lookup is by exact key / known field on a small set — that is a database index (`WHERE id = ?`), see db-design, not a search engine. Search earns its complexity only for ranked, fuzzy, or free-text retrieval.

## The Index Is Derived, Never the Source of Truth

The single most important rule: **the search index is a denormalized, rebuildable projection of data that lives authoritatively elsewhere** (the transactional DB). It is eventually consistent and disposable.

- Never write user data *only* to the search engine. If the index is lost, it must be reconstructable from the source of truth by a full reindex.
- The index is *denormalized on purpose* — flatten the joins at index time so query time is a single fast lookup. This is the opposite of the normalized source schema (db-design owns that), and that is correct.
- Accept eventual consistency: a document may be ~seconds stale after a write. If a use case cannot tolerate any staleness, read it from the DB, not the index.

## Keeping the Index in Sync — The Hard Part

Search bugs are usually sync bugs. Three strategies, increasing robustness:

1. **Dual-write** (handler writes DB then index) — simplest, but the two can diverge on partial failure. Avoid for anything important (same dual-write hazard as messaging-queues).
2. **Outbox / CDC** — DB write emits an event (transactional outbox or change-data-capture like Debezium); a consumer updates the index. Robust, eventually consistent, the production default.
3. **Periodic full reindex** — rebuild from scratch on a schedule and on demand. Always have this path; it is the disaster-recovery floor and how a mapping change ships.

**Reindex without downtime: alias swap.** Build into a new index, then atomically repoint a read alias from old → new. Never reindex in place against live traffic.

## Full-Text — Analyzer Chain Decides Everything

Relevance is mostly determined *at index time* by the analyzer (how text becomes searchable tokens), not at query time.

- **Tokenization + normalization**: lowercase, strip punctuation, split on word boundaries. The query must use the *same* analyzer as the field, or "iPhone" won't match "iphone".
- **Stemming / lemmatization**: "running" → "run" so a search for "run" hits it. Language-specific; the wrong language analyzer silently kills recall.
- **Stop words**: dropping "the/a/of" shrinks the index, but breaks phrase queries like "to be or not to be" — tune per corpus.
- **Synonyms**: "laptop" ⇄ "notebook". A synonym graph at index or query time is the highest-leverage relevance fix for domain vocabulary.
- **N-grams / edge-grams**: power autocomplete and typo tolerance — index prefixes so "lap" matches "laptop" as the user types.

### Relevance scoring — BM25 and boosts

- **BM25** is the default ranking function (term frequency × inverse document frequency, length-normalized). It is what modern engines use out of the box; understand it before fighting it.
- **Field boosts**: a match in `title` should outrank a match in `body` — boost the field. This is the most common, highest-impact tuning knob.
- **Measure relevance, don't eyeball it.** Build a judgment set (queries → known-good results) and track nDCG/MRR; tune against the metric, not against the one query a stakeholder complained about.

## Vector / Semantic Search — When Keywords Aren't Enough

Keyword search fails when the query and document use *different words for the same idea* ("car" vs "automobile", a question vs a statement). Embedding-based retrieval fixes that.

- **Embeddings**: a model maps text → a high-dimensional vector; semantically similar text lands nearby. Query and documents embed with the *same* model — mismatched models give garbage.
- **ANN index**: exact nearest-neighbor is too slow at scale; an approximate index (HNSW, IVF) trades a little recall for huge speed. Tune `ef`/`nprobe` for the recall/latency point needed.
- **Hybrid retrieval** is usually best: run BM25 *and* vector search, fuse the rankings (Reciprocal Rank Fusion). Keyword nails exact terms/IDs; vector catches paraphrase. Neither alone wins across a realistic query mix.
- **Chunking matters** for long documents: embed passages, not whole docs, or the vector averages into mush. This is also the retrieval half of RAG — but assembling retrieved chunks into a grounded LLM prompt is llm-patterns, not this skill.

## Faceting, Filtering, Pagination

- **Filters are not queries.** A filter (`category = "shoes"`, `price < 100`) is a boolean include/exclude with no relevance contribution and is cacheable — keep it out of the scoring query for speed.
- **Facets** = filter counts for the UI ("Shoes (42)"). Compute as aggregations; they drive the filter sidebar.
- **Paginate with `search_after` / cursors**, not deep `from/offset` — deep offset pagination forces the engine to sort the whole prefix and degrades hard past a few thousand results.

## Anti-Patterns (reject in review, fix on sight)

- **Search engine as system of record** — user data only in Elastic; one node loss = data loss.
- **Query analyzer ≠ index analyzer** — silent zero-recall; the field and the query must analyze identically.
- **Dual-write sync with no reconciliation** — index drifts from the DB and nobody notices until a user does.
- **Reindexing in place on live traffic** — partial results during rebuild; use alias swap.
- **Tuning relevance by eyeballing one query** — fix one, break ten; measure with a judgment set.
- **Vector-only for everything** — fails on exact IDs, SKUs, error codes; hybrid beats pure vector on mixed queries.
- **Deep offset pagination** — `from: 10000` melts the engine; use `search_after`.
- **Embedding whole long documents** — meaning averages out; chunk into passages.
- **Stop words stripped under a phrase-query feature** — breaks "to be or not to be".

## Tools per surface (2026 defaults)

| Need | Default | Alternatives |
|---|---|---|
| General full-text at scale | Elasticsearch / OpenSearch | Solr |
| Fast, low-ops, typo-tolerant search | Meilisearch, Typesense | Algolia (hosted) |
| Search inside an existing Postgres | Postgres FTS (`tsvector`) + `pg_trgm` | ParadeDB |
| Vector / semantic | pgvector, Qdrant, Weaviate | Milvus, Elasticsearch kNN |
| Embeddings model | provider embedding API / open model | sentence-transformers |
| CDC sync DB → index | Debezium, logical replication | transactional outbox + consumer |

## Pairs With

- **db-design** — the normalized, transactional source of truth; this skill is the derived denormalized index built from it. The sync seam between them is the whole relationship.
- **redis** — caching hot queries/facets in front of the engine; ephemeral, not the index itself.
- **llm-patterns** — vector retrieval is the "R" of RAG; this skill owns retrieval, llm-patterns owns prompt assembly and grounding.
- **messaging-queues** — the CDC/outbox event stream that drives index sync; same dual-write hazard, same outbox cure.
- **observability** — query latency, recall metrics, reindex duration, and index-lag are the search golden signals.

## See also

- Elasticsearch: *The Definitive Guide* — analysis, relevance, BM25.
- *Relevant Search* (Turnbull & Berryman) — analyzer chains, boosting, judgment-set tuning.
- HNSW paper (Malkov & Yashunin) — the dominant ANN index.
- *Introduction to Information Retrieval* (Manning et al.) — inverted index, ranking, evaluation (nDCG/MRR).
