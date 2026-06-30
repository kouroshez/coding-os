<!-- domain:META | layer:engineering | ssot:true | updated:2026-06-30 -->
# Derived-Store Coherence Audit — 2026-06-30

The `tasks` board drift (a deleted task file leaving a ghost row in the panel) is one
instance of a general question: across the 58-table `coding-os.db`, which **derived**
stores prune when their source-of-record disappears, and which **append-only** stores
are bounded? This audit answers both, names the gaps, and fixes them.

## Two invariants every derived store must obey

1. **Prune-on-delete** — when the source-of-record (a file, a parent row) is removed, the
   derived rows must follow, via FK `ON DELETE CASCADE`, an `AFTER DELETE` trigger, or an
   event/reconcile sweep.
2. **Retention** — every append-only event/telemetry store must be bounded (cap, TTL, or
   rollup-then-truncate) so it cannot grow without limit.

## Reference implementation: the graph

`graph_os` is the model the rest of the store should follow. A deleted file is pruned
immediately by `auto-graph-reconcile-shell.sh` (catches `rm`/`mv`/`git rm`) →
`prune_deleted_path.py` → `DELETE FROM graph_nodes` → FK `CASCADE` to edges/evidence. A
removed symbol is pruned by prune-before-reindex (`delete_nodes_for_file`). A full
`cos graph-reindex` reconciles stale paths; `cos_graph_doctor --fix` sweeps residual
orphans. Result: no orphan/ghost class.

## Findings

### Class 1 — orphan-on-delete

| Store | On source delete | Verdict |
|---|---|---|
| graph nodes / edges / evidence | rm hook + FK CASCADE + reconcile + doctor | ok (reference) |
| FTS ×4 (tasks / observations / doc_chunks / graph_nodes) | `AFTER DELETE` triggers | ok |
| embedding_outbox | drain-time existence check | ok |
| document_chunks (edit path) | delete-then-insert | ok |
| **tasks** | `sync_all` is upsert-only — never prunes | **gap** |
| **document_chunks (file-delete path)** | pruned only by a full `index_docs`; the single-file reindex hook and the nightly do not | **gap** |
| **embeddings** | no FK / trigger; `memory_gc()` hunts them but is not scheduled | **gap** |
| **task_status_history / task_outcomes / task_edit_history** | no FK, no trigger | **gap** (orphan once a task row is deleted) |
| graph_vec | tolerates orphans; harmless (rebuilt DROP+CREATE) | minor |

### Class 2 — unbounded growth

`log_events`, `agent_metrics`, `retrievals`, `outcome_history`, `retrieval_router_log`,
`project_trajectory`, `session_summaries`, `formula_dispatches`, `backtrack_events` have
no retention. `observations` is partially managed (working memory expires via `decay.py`).
All are small today (150–9,000 rows); SQLite handles this for years. Deferred — see below.

## Fix plan (in flight: TASK-715)

1. **Tasks prune-on-delete.** `sync_all` prunes rows whose file is absent — guarded to a
   full, uncapped walk only (a single-file sync must never prune its siblings; the
   `cos graph-reindex` lesson). The same migration adds `AFTER DELETE` triggers on
   `task_status_history`, `task_outcomes`, `task_edit_history` (mirroring the existing
   `tasks_deps_ad` trigger) so a pruned task row cascades.
2. **Doc-chunk reconcile.** A nightly task invokes the existing `_delete_orphaned_chunks`
   so chunks for deleted docs are pruned without waiting for a manual `make docs-index`.
3. **Schedule `memory_gc()`.** The existing, tested GC (orphan embeddings + trash
   observations + stale edges) runs in the nightly. Reuse, not new triggers.
4. **error_sweep `event_class`.** Log events carry an `event_class` (`fault | policy |
   audit`); hook BLOCK events are `policy`; the sweep files only `fault`. Hook BLOCKs are
   policy enforcement succeeding, not bugs — they must never become board tasks.

## Deliberately deferred (anti-overengineering)

- **Unified retention framework.** The unbounded stores are tiny and not near any limit;
  a config-driven retention registry now is speculation. Revisit per-store if one actually
  approaches a real bound. Fix 4 already curbs the fastest grower (`log_events`).
- **Dedicated `auto-task-reconcile` rm/mv hook.** The full-sync prune (fix 1) covers the
  rare hand-delete; an instant per-delete hook is unearned while tasks are archived, not
  deleted.
- **Store registry + `cos doctor --stores`.** Elegant, but four targeted fixes close the
  current gaps; the registry is a framework for a problem already solved.
