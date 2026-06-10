<!-- domain:ALL | layer:engineering | ssot:false | updated:2026-05-23 -->
# Audit — graph_os Health Issues (2026-05-23)

Forensic root-cause for the three doctor-reported categories: `dangling_source: 20495`, `orphaned_nodes: 1542`, `self_loops: 48`. Total: `node_count=42869`, `edge_count=98622`. 20.8 % of edges are dangling.

## Evidence

Sample dangling (`source_uid: null`, target external):

| edge_id | source_uid | target_uid |
|---|---|---|
| 1201318 | null | `code:external:unresolved:out.sort` |
| 1201243 | null | `code:external:typing:Any` |
| 1201319 | null | `code:external:unresolved:getattr` |
| 1201320 | null | `code:external:unresolved:hasattr` |
| 1201245 | null | `code:external:unresolved:str` |

Sample orphans: shields.io README badges (`doc:external:https://img.shields.io/badge/...`) + ex-doc files (`docs/features.md`, `docs/architecture.md`).

Sample self-loops:
- `code:method:src/core/graph_os/backends/kuzu_backend.py::KuzuBackend.close` → calls (self)
- `doc:file:CHANGELOG.md` → links_to (self) — anchor link rendered to file uid
- `code:function:tests/test_claude_dispatcher_options.py::_literal_strings` → calls (self) — test fixture

## Root cause per category

### 1. `dangling_source` (20 495 edges = 20.8 %)

**Initial hypothesis (Wave-1 agent):** code_python.py emits edges without ensuring stubs exist for the target — `_promote_stubs` is missing.

**Revised finding (TASK-017 verification):** `_promote_stubs` is **already called** at [code_python.py:728](../../../src/core/graph_os/extractors/code_python.py) (and 462, 472). Source + target stubs are minted during extraction. The real bug is that **`src/scripts/prune_deleted_path.py:37` opens its own `sqlite3.connect()` without `PRAGMA foreign_keys = ON`**, so the schema-declared `ON DELETE CASCADE` on `graph_edges_v12.{source,target}_id` is silently skipped. Every PostToolUse-Bash invocation of the auto-prune hook (`auto-prune-deleted-files.sh`) on a `rm`/`git mv` deletes graph_nodes but leaves their edges orphaned — 20 k accumulated since the v12 migration.

Demonstrated with a 5-line SQLite fixture:

```
before-no-PRAGMA: edges = 3
after-delete-no-PRAGMA: edges = 3 (orphaned!)
after-delete-PRAGMA-on: edges = 1 (CASCADE fired)
```

Fix landed in TASK-017 — single `conn.execute("PRAGMA foreign_keys = ON")` added after the `sqlite3.connect()` call. Existing 20 k orphans drained by `cos_graph_doctor(fix=True)` (the doctor already has the purge capability at [tools/graph.py:2297-2306](../../../src/core/graph_os/tools/graph.py)) — see Phase 4 follow-up.

### 2. `orphaned_nodes` (1 542)

Two sub-classes:

- **README shields.io badges** (`doc:external:https://img.shields.io/badge/...`) — `md_links.py` ingests them as `doc:external` nodes during the README markdown pass but they receive no inbound contains-edge from the README file (no `image` edge-type emitted). Cheap fix: extend `md_links.py` to emit a `references` edge from the parent doc to each external image, or filter `img.shields.io` from the external-node emission entirely (badges have zero analytic value).
- **Reachable-from-nothing doc files** (`docs/features.md`, `docs/architecture.md`) — these existed at some point and were indexed, then later renamed/removed without the auto-prune hook firing (likely because the rename happened outside Claude Code's PostToolUse path: shell mv, git checkout, manual edit). The CONTAINS spine from the repo-root never re-emitted for them.

Cleanup option: `cos_graph_doctor(fix=True)` already has node-purge logic — extend it (or run `cos graph-reindex --force` once) to drop orphans. Long-term: the file-watcher hook should also fire on `git checkout` boundaries.

### 3. `self_loops` (48)

Three legitimate sources, none truly bugs:

- **Anchor-only markdown links** (e.g. `CHANGELOG.md` linking to `#section` in itself) — `md_links.py:209` resolves these to `doc:file:<path>#<anchor>` which is the same uid as the source. This is intentional but masquerades in the doctor report as a self-loop. Fix: tag with `edge_type='anchor_link'` in the doctor SQL so the dashboard can filter them.
- **Test-fixture call-graphs** that legitimately recurse — `_literal_strings` calls itself in `test_claude_dispatcher_options.py`. Real recursion, no fix.
- **Retired Kuzu backend symbols** — `kuzu_backend.py::KuzuBackend.close` calls itself. The Kuzu backend was retired 2026-05-18 per ADR-0002 but the file lingered until next reindex. Stale; will drop when the file is removed.

Low impact — defer behind a "is this a real bug?" tag in the doctor UI.

## `max budget` investigation

User reports the graph visualisation never reaches 100 % node coverage on the `max` preset. Backend evidence:

- [src/core/web/routes/graph.py:210](../../../src/core/web/routes/graph.py) — hard-coded default `max_nodes: int = Query(500)`. Not "unlimited".
- [src/core/graph_os/tools/graph.py:1423-1429](../../../src/core/graph_os/tools/graph.py) — equal-share quota across `_AUTO_BLEND_BUCKETS` (7 semantic buckets) → 500 / 7 ≈ 71 edges/bucket, with deleted nodes silently filtered out (line 1429) so the actual returned count is < 500.
- BFS walk on `depth=2` further constrains nodes (edges-budget is the hard cap, not nodes).

Mismatch: the UI offers a `max` preset but the route caps at 500. Phase 5 will replace the enum with an explicit `focus_uid + depth_hops + render_budget` triplet and surface "X/Y nodes shown" in the canvas so the cap is transparent.

## Fix candidates (ordered by leverage)

| # | Fix | Where | Diff radius | Status |
|---|---|---|---|---|
| 1 | Enable `PRAGMA foreign_keys = ON` in `prune_deleted_path.py` | `src/scripts/prune_deleted_path.py:37` | 1 line + comment | **DONE — TASK-017** |
| 2 | Drain historical 20 k orphans | `cos_graph_doctor(fix=True)` (capability exists at `tools/graph.py:2297-2306`) | 0 (CLI invocation) | **Phase 4** |
| 3 | Filter shields.io badge URLs from `md_links.py` external emission | `src/core/graph_os/extractors/md_links.py` | ~10 lines | Phase 5 follow-up |
| 4 | Tag anchor self-loops as `anchor_link` in doctor SQL | `tools/graph.py:2430-2447` | ~10 lines | Phase 6 (doctor UI) |
| 5 | Replace `max_nodes=500` hard cap with progressive disclosure | `src/core/web/routes/graph.py:210` + `GraphCanvas.tsx` | ~80 lines | Phase 9 |

## Open questions

- **Other peer connections without PRAGMA?** A grep for `sqlite3.connect` outside the backend turned up `prune_deleted_path.py` (fixed) + `session_enrich.py` (does not delete from graph_nodes — safe). Should add a lint that flags any direct `sqlite3.connect()` that DELETEs from graph_nodes without first calling the PRAGMA.

## References

- [src/scripts/prune_deleted_path.py](../../../src/scripts/prune_deleted_path.py) — fixed in TASK-017
- [src/core/graph_os/backends/sqlite_backend.py](../../../src/core/graph_os/backends/sqlite_backend.py) — reference connection bootstrap
- [src/core/graph_os/tools/graph.py](../../../src/core/graph_os/tools/graph.py) — doctor SQL
- [src/core/hooks/auto-prune-deleted-files.sh](../../../src/core/hooks/auto-prune-deleted-files.sh) — invoking hook
- [docs/tasks/TASK-017-fix-prune-deleted-path-missing-pragma-foreign-keys-on.md](../../tasks/TASK-017-fix-prune-deleted-path-missing-pragma-foreign-keys-on.md)
