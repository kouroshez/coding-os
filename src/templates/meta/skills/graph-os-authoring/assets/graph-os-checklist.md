<!-- domain:META | layer:asset | ssot:false | updated:2026-06-04 -->
# graph_os Authoring Checklist

Run when adding a node/edge type, an extractor, or touching the backend.

## Extractor invariants
- [ ] `bash scripts/new_extractor.py --lang <l>` used (or matches its shape).
- [ ] `uid` is deterministic for the same symbol → upsert is idempotent.
- [ ] Short-circuits unchanged files via `file_index_state` content hash.
- [ ] Returns typed `Node`/`Edge` — no raw dicts.
- [ ] Registered in the reindex dispatcher.

## Backend discipline
- [ ] Tool layer stays backend-agnostic — no raw SQL/Cypher leaks into `cos_graph_*` callers.
- [ ] `file_index_state` writes are append-only.
- [ ] Confidence scored on inferred edges (low-confidence clustered, not asserted).

## Coverage
- [ ] New edge/node kind documented in graph-hallucination-cures.md if it powers a `cos_graph_*` tool.
- [ ] `cos_graph_*` envelope still `ok`/`fail` (Rule 13) for any new graph tool.

## Verify
- [ ] `uv run --extra graph_os pytest src/core/graph_os/tests/ -q`.
- [ ] `cos graph-reindex --force` after extractor-code changes (plain reindex skips by content hash).
- [ ] `cos graph-doctor` clean.
