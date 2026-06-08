<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-06-07 -->
# Concept Graph (co_edit / concept_link)

Purpose: Contract for the `concept_graph` table — the lightweight file/concept
adjacency list in `coding-os.db`. It exists to surface "files often edited
together" (`co_edit`) and "concepts that co-occur in lessons" (`concept_link`).
Producer: `src/core/thinking_os/graph.py`; GC: `src/core/thinking_os/memory_gc.py`;
consumer: `src/core/thinking_os/session_enrich.py` (the digest "Co-edited" line).
Read when: editing `record_co_edit`, `build_concept_links`, or the memory GC.
Skip when: working on the structural code graph (that is `graph_os`, a different,
richer system — prefer it for real dependency/impact queries).

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## Why this contract exists (the 260 MB incident)

`record_co_edit` originally linked every edited file to **all** other files
modified in the session. A long multi-file session is therefore O(N²) in edges,
and edges **accumulated across every session forever** with no pruning. On the
meta-repo this reached **270k `co_edit` rows over 791 files** — a near-complete
graph (zero signal) that, with full absolute-path keys and three indexes, bloated
`coding-os.db` to **267 MB**. A near-complete graph is useless *and* huge.

## The bound contract (mandatory)

1. **Bounded fan-out.** `record_co_edit(..., max_links=8)` links the new file to
   only the `max_links` **most-recently-edited** other files in the session
   (`GROUP BY files_modified ORDER BY MAX(created_at) DESC LIMIT max_links`).
   Growth is O(N·max_links), not O(N²). Recency is also better signal — files
   edited close in time are more genuinely related than session-wide pairs.
2. **GC prune (density backstop).** `gc_memory` deletes `co_edit` edges with
   `weight <= 1.0` (seen once, never reinforced = noise) that are stale
   (`updated_at` older than 30 days). Reinforced (`weight > 1.0`) or recent edges
   survive. This keeps the table from trending back toward a complete graph.
3. **Reinforcement, not duplication.** `UNIQUE(source, target, edge_type)` +
   `ON CONFLICT … weight = weight + 0.1` means a repeat co-edit bumps weight, it
   does not add a row. `weight` is therefore the strength signal GC and ranking use.

`concept_link` (from `build_concept_links`) is naturally bounded (concept pairs
over the small `learned_patterns` set) and needs no fan-out cap.

## Cleanup of a bloated graph

```sql
DELETE FROM concept_graph WHERE edge_type='co_edit';  -- drop the dense junk
-- then reclaim file space (needs a quiet moment — no other DB connection):
VACUUM;
PRAGMA wal_checkpoint(TRUNCATE);
```
The bounded producer + GC prune then keep it small as it rebuilds.

## See also
- [learning-extraction.md](learning-extraction.md) — the learning loop (separate concern).
- [graph_os-queries.md](graph_os-queries.md) — the structural code graph (use it for real impact/rename).
