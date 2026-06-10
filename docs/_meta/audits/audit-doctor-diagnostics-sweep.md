<!-- domain:ALL | layer:engineering | ssot:false | updated:2026-05-23 -->
# Audit — Doctor / Diagnostics Sweep (2026-05-23, TASK-024)

User asked: (1) why does sqlite tab show `metrics/patterns/audit_log` as absent? (2) what are the 48 self-loops? (3) are the Health & charts numbers real or mock? (4) sweep every Diagnostics panel for mock data.

## 1. sqlite "absent" — root cause

`src/core/web/routes/health.py::_DB_TABLES_OF_INTEREST` listed **legacy names** that never existed in any migration:

| UI label | Actual table in DB | Status |
|---|---|---|
| `metrics` (absent) | `agent_metrics` (270 rows) | renamed in the migration v-series |
| `patterns` (absent) | `learned_patterns` (0 rows) | full-form name in v7+ |
| `audit_log` (absent) | `doc_audit_trail` (0 rows) | scoped to docs in v9+ |

The route checked `SELECT COUNT(*) FROM metrics` etc. → table missing → marked "absent". Fixed by replacing the list with the canonical migration names. The "0 rows" for `learned_patterns` and `doc_audit_trail` is the REAL state — these tables exist but no rows have been written yet (memory pipeline only revived in TASK-016 + cron writes nothing until observations accumulate).

## 2. 48 self-loops — full categorization

```
SELECT n.uid, e.edge_type FROM graph_edges_v12 e
JOIN graph_nodes n ON n.id = e.source_id
WHERE e.source_id = e.target_id;
```

| Category | Count | Verdict | Sample |
|---|---|---|---|
| Anchor markdown links (`#section` resolving to file uid) | 3 | **legitimate** — internal navigation | `doc:file:CHANGELOG.md → links_to (self)` |
| `@mcp.tool` decorator wrapper | 9 | **extractor artifact** — the decorator transforms the function into a wrapper that calls the original; AST visitor records this as a self-call | `cos_task_board → calls (self)` |
| Logger method wrappers (`debug/info/warn/error/fatal/ok`) | 11 | **extractor artifact** — `_KVLogger.debug` calls `logging.Logger.debug` (inherited); same-name resolution collapses to self | `ScopedLogger.debug → calls (self)` |
| Inner recursion (`.walk` / `.dfs` / nested DFS) | 4 | **legitimate** — real recursive walkers | `validate_dependencies_no_cycle.dfs → calls (self)` |
| `__init__` super() chain | 3 | **extractor artifact** — `super().__init__()` resolves to same name on parent; AST visitor can't disambiguate | `InitError.__init__ → calls (self)` |
| Dict-like proxies (`.items/.keys/.values`) | 3 | **extractor artifact** — `StackLoadResult.values` calls `dict.values` on its inner dict; name collision | `SkillRegistry.values → calls (self)` |
| `.close/.start/.shutdown/.clear/.warm_start` methods | 8 | **extractor artifact** — methods call inherited / parent same-name; same shape as logger wrappers | `KuzuBackend.close → calls (self)` |
| Test fixture `_literal_strings` | 1 | **legitimate** — actual fixture recursion in test data | `tests/test_claude_dispatcher_options.py::_literal_strings` |
| Misc (verify_phase_c_e2e.run, formula_composer._deep_merge, others) | 6 | **mixed** — `_deep_merge` is real recursion, others are super-call artifacts | various |

**Summary:** ~9 legitimate (anchor links + real recursion), ~39 extractor artifacts from name-collision in AST resolution.

**Fix path (not landed in this task):** the AST visitor at `code_python.py::_resolve_call` should compare the resolved callee uid to the caller uid; when equal *and* the call is at the AST node level (not a recursive call inside the body), skip the edge. Diff radius ~15 lines. Defer behind a tagged "is this a real bug?" view in the doctor UI.

## 3. Health & charts — is it real?

**Real, not mock.** Source:

- `src/core/web/_deps.py::make_metrics_dep` (lines 42-56) wraps every route handler as a FastAPI dependency that calls `prom.inc_counter("cos_web_requests_total{route=…}")` before the handler runs and `prom.record_timing(...)` on completion.
- DoctorPage `HealthTab` polls `GET /metrics` every 2 s, parses the Prometheus text format, and reduces over `cos_web_requests_total` samples for the total.
- The "numbers move" effect = **the SPA itself polls /api/* in the background**: `LiveStatus` (presence), `HealthAlarmBar` (doctor+health every 30 s), Dashboard tiles, Cognition trace lists. Every poll increments the counter. From the user's point of view they "did nothing" but their browser is sending requests on a timer.

Fix landed: the Health & charts header now carries the caption `real Prometheus counters from FastAPI middleware — the numbers move because the SPA itself polls /api in the background`.

## 4. Mock / fake / hardcoded data sweep

Grepped `Math.random`, `faker`, `mock`, `placeholder`, `TODO`, `hard.?coded` across `src/core/web/ui/src/{pages,features}/`. Findings:

| File:line | Match | Verdict |
|---|---|---|
| `HubHome.tsx:261,730,757,864` | `placeholder="..."` | HTML input-attribute hint, **not data** — clean |
| `LogsPage.tsx:179,180,188,189,197,199` | `placeholder="..."` | HTML input hints — clean |
| `ObservabilityPage.tsx:165` | `placeholder="ses-claude-..."` | input hint — clean |
| `cognition/ChatList.tsx:107`, `ChatView.tsx:330`, `TraceList.tsx:85`, `observability/HookStream.tsx:178` | `placeholder=...` | input hints — clean |
| **`DoctorPage.tsx:386`** | `errorsHistory: prev.errorsHistory, // placeholder — fill if backend exposes errors` | this series stays empty because `/metrics` does NOT yet expose a 4xx+5xx counter; **not fake, just always-zero**. Either implement the backend counter (small Phase 11) or remove the chart row. |

No actual mock-data generators. No `Math.random()` synthesising series. No fixture data masquerading as live. The diagnostics panel is honest — the only soft spot is the placeholder errors history which is genuinely empty until the backend exposes the data.

## 5. Graph budget loading order (user question)

Reading `cos_graph_export(root_uid=…, mode=…, max_nodes=N)` at `src/core/graph_os/tools/graph.py:1385-1456`:

```
mode='auto' (default):
  per_bucket = max_nodes / len(_AUTO_BLEND_BUCKETS)   # ~71 if max=500
  for bucket in _AUTO_BLEND_BUCKETS:
      edges += backend.list_edges(edge_types=bucket, limit=per_bucket)
  edges = edges[:max_nodes]                            # trim to budget
  nodes = unique source+target uids → fetch node rows
  for n in nodes:                                      # spine walk
      ancestors = _contains_ancestors(n.uid)
      nodes ∪= ancestors                                # so tree stays connected
  return (nodes, edges)
```

**Order within each bucket:** `(confidence DESC, id ASC)` — high-confidence edges land first.

**It is NOT BFS from root.** Even with a `root_uid` parameter, the SPA's overview view (no root selected) hits this bucket-quota code path. The "spine walk" adds ancestor folders so the tree stays connected, but the initial sample is not depth-ordered.

**Implication for the user's mental model** ("max should be 100%"):
- Current behaviour: max=20 000 means "top 20 000 edges by confidence + spine". At 78 173 edges total in this repo, that's ≈26 % coverage at "max" overview, well above the previous 3.5 %.
- For TRUE 100 %, the SPA would need to send `max_nodes=∞` AND the backend would need to drop the cap on edge counts. Sigma.js can render the full 41 k nodes but layout time becomes noticeable.
- For "tree-based loading" (which the user explicitly asked about), the right primitive is a rooted BFS — pass `root_uid="folder:."` and `mode="containment"`. The backend already supports this and follows `CONTAINS` edges depth-first; the SPA can wire it as the default for the Containment view (Phase 9 follow-up).

## References

- [src/core/web/routes/health.py](../../../src/core/web/routes/health.py) — `_DB_TABLES_OF_INTEREST` (fixed)
- [src/core/web/_deps.py](../../../src/core/web/_deps.py) — `make_metrics_dep` (real counter)
- [src/core/web/ui/src/pages/DoctorPage.tsx](../../../src/core/web/ui/src/pages/DoctorPage.tsx) — Health & charts caption (added)
- [src/core/graph_os/extractors/md_links.py](../../../src/core/graph_os/extractors/md_links.py) — root label (`.` → `repo-root`)
- [src/core/graph_os/tools/graph.py](../../../src/core/graph_os/tools/graph.py) — `_export_blend` budget logic (lines 1385-1456)
- [docs/tasks/TASK-024-fix-health-db-wrong-table-names-audit-diagnostics-for-mock-d.md](../../tasks/TASK-024-fix-health-db-wrong-table-names-audit-diagnostics-for-mock-d.md)
