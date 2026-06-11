<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-05-27 -->
# MCP Error Envelope — `cos_*` Tool Response Contract

Purpose: Canonical response shape for every `cos_*` MCP tool exposed by
[src/core/thinking_os/server.py](../../src/core/thinking_os/server.py). The envelope
gives consuming agents enough structure to decide whether to retry, escalate,
or surface an error to the user — without parsing prose.

Read when: Adding a new `cos_*` tool · modifying an existing one · writing

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

tests that assert tool return values · debugging agent recovery behavior.

## Why an envelope

Before this contract each tool returned `json.dumps(result)` — a raw payload
that an agent could not tell apart from a failure. Mapping to the Claude
Certified Architect exam guide (Task Statement 2.2) and to proven production
patterns (zibalvpn R3), the envelope:

- Distinguishes **success** from **error** with a single `ok` boolean so the
  agent never has to guess from content shape.
- Carries an **error category** so the agent can pick the right recovery
  (retry vs escalate vs surface).
- Carries a **retryable** flag so the agent doesn't waste turns on errors
  that cannot be resolved by retry (e.g. missing information).

## Envelope shape

### Success

```json
{
  "ok": true,
  "data": {
    "<payload-keys>": ...,
    "meta": {
      "layer": "memory" | "docs" | "tasks" | "metrics" | "routing" | "graph" | "health" | "learning" | "audit",
      "tokens_estimated": <int>,
      "truncated": <bool>,
      "<truncated_*>": ...
    }
  }
}
```

`data` is whatever the tool produced — a dict, a list, a scalar, or even
`null`. Consumers should drill through `data` rather than the top level.

#### `data.meta` — diagnostics block (set by `ok()`, callers cannot spoof)

| Key | Type | Meaning |
|---|---|---|
| `layer` | str | Which retrieval layer answered (`memory` / `docs` / `tasks` / `graph` / …). Callers supply this via `ok(data, meta={"layer": ...})`. |
| `tokens_estimated` | int | Script-aware token estimate of the serialized response — ASCII ~4 chars/token, non-ASCII counted ~1 token/char so non-Latin (CJK/Arabic/Cyrillic) is not undercounted. Set by `ok()`; callers MUST NOT set manually. |
| `truncated` | bool | `True` iff `_apply_token_budget` (or `_trim_coherent_subgraph` for graph-export shape) actually shrank the body. `False` for no-op trims so agents trust the signal. |
| `truncated_results_from` / `truncated_results_to` | int | Original + kept count when `data.results` was tail-trimmed. Same pattern (`<key>_from` / `<key>_to`) for every key in `_TRIMMABLE_LIST_KEYS` (`neighbours`, `references`, `edges`, `nodes`, `processes`, `call_sites`, `import_sites`, `doc_references`, `test_references`, `string_literals`, `external_targets`, `branches`, `steps`, `http_routes`, `mcp_tools`, `grpc_endpoints`, `event_handlers`, `websocket`, `nodes_top`, `samples`, `rows`, `entries`, `cycles`, `untested`, `dead`). |
| `truncated_edges_by_type` | dict | Per-bucket trim record `{kind: {from, to}}` for `edges_by_type` dict-of-lists. |
| `truncated_string_fields` | list[str] | F#5 final safety-net — names of **large** scalar fields (≥ `_SCALAR_TRIM_FLOOR_CHARS`, 200) shortened with `…[truncated]`. Small load-bearing scalars (`scope`, `risk_level`, `status`, …) are NEVER trimmed: truncating a 4-char `"high"` cannot recover budget and only destroys signal, so the safety-net skips any string below the floor. |
| `truncated_subgraph` | bool | Set when `_trim_coherent_subgraph` cut a `{nodes, edges}` body (graph-export shape). Pairs with `truncated_nodes_from/to` + `truncated_edges_from/to` so the agent can detect coherent (proportional) trim vs catastrophic shrink. |
| `envelope_unshrinkable` | bool | Surfaced when every trim ladder ran and the payload still exceeded budget — caller should log + investigate. Never set on the web opt-out path (`apply_budget=False`), where the trimmer is skipped by design. |
| `resolved_from` | str | W7.2 / R4-01. For uid-accepting tools (`context`, `impact`, `references`, `rename_plan`, `trace`, `similar`). One of `"direct"` (exact uid match) / `"path_prefix"` (raw path resolved via `code:file:` / `doc:file:` / `folder:` prefix) / `"fuzzy_fts5"` (FTS5 label fallback — answer may be wrong symbol, agent should verify). For `cos_graph_path` the keys are `source_resolved_from` + `target_resolved_from`. |
| `default_kinds_picked` | bool | W7.3 / R4-02. `cos_graph_references` only. `True` when the caller passed empty `kinds` and the tool picked the per-node-kind default (class → `constructs+has_param_type+inherits_from+…`, function → `calls+accesses_field+imports+…`, file → `imports+links_to+contains+…`, doc_file → `links_to+cites_heading+…`, dependency → `requires+imports+…`). |
| `node_kind` | str | W7.3. `cos_graph_references` only. The `kind` of the resolved root node — lets the caller verify that the per-kind defaults are appropriate. |
| `semantic_scope` | str | `cos_graph_impact` only. `"transitive_depth_N"` so the caller can tell direct callers (`depth=1`) apart from N-hop transitive ones — disambiguates the F1 disagreement between rename_plan / references (direct) and impact (transitive). |
| `fixable_categories` | list[str] | `cos_graph_doctor` only. Categories that `fix=True` actually deletes — `["stale_paths","malformed_uid_path","dangling_source","dangling_target"]`. Distinct from `informational_categories` which surface for visibility but never trip `healthy=false`. |
| `informational_categories` | list[str] | `cos_graph_doctor` only. Categories surfaced as info — `["orphaned_external_unresolved"]` (stdlib / 3rd-party stub orphans, expected). These are listed in `issues` with `severity: "info"` and ignored by the `healthy` boolean. |

The trimmer strips and re-computes `tokens_estimated`, `truncated`, and every
`truncated_*` key on each call; callers cannot inject false values via the
`meta=` kwarg.

#### Token budget tiers

| Tier | Constant | Trim strategy | Applies to |
|---|---|---|---|
| Default (agent context) | `TOKEN_BUDGET_CHARS = 32_000` | `_apply_token_budget` — per-key shrink ladder (results/neighbours/references/…), then `edges_by_type` buckets, then F#5 string truncation. Each list trim re-checks the **committed** envelope (including the `truncated_<key>_from/to` marker bytes it just added) and shrinks one element further if still over — so the ladder never returns a body that is marginally over budget and falls through to maul scalars. The over-budget trigger and every probe compare a **token-normalised** size (`max(len, est_tokens×4)`, identical to raw length for ASCII) so non-Latin payloads trim at the real ~8 K-token budget, not a raw-char proxy. | Every `cos_*` tool whose response does NOT have both `nodes:list` and `edges:list` |
| Graph subgraph (OOM safety) | `GRAPH_SUBGRAPH_BUDGET_CHARS = 5_000_000` | `_trim_coherent_subgraph` — binary-search top-K nodes by incident degree, keep only edges between kept nodes | `cos_graph_export` and any other tool emitting `{nodes, edges}` |
| Web/browser opt-out | `ok(..., apply_budget=False)` | none — the token-budget trimmer is skipped entirely | FastAPI web routes that re-use a `cos_*` tool function but serve a **browser** (not token-limited). The board's `/api/board/list` threads `cos_task_board(apply_budget=False)` straight into `ok()`, so a large board renders without tripping the 32 KB agent cap or its `envelope_unshrinkable` fall-through. |

Rationale for the second tier: `cos_graph_export` describes a whole
subgraph (Hub UI's CONTAINS spine, 1094 nodes / 1444 edges typical for
this repo ≈ 1 MB pretty-printed). The agent-context cap (32 KB) is the
wrong constraint — it would either zero out `edges` (W6.6 regression,
fixed by [139f239] / [20feb59]) or yield a 59-node incoherent slice.
The 5 MB ceiling is an OOM safety net: any normal request passes
through untouched; only pathological agent requests (max_nodes=10000
+ no edge-types filter) trip the coherent trim, and even then the
caller receives a connected subgraph the Hub UI can render. The
caller's `max_nodes` / `max_hops` parameters (G35 hard-caps
`max_nodes ≤ 2000`) are the primary volume controls; the envelope
is the safety net.

**Third tier — `apply_budget=False` (web opt-out).** The 32 KB default is
an *agent-context* budget: it stops a tool response from flooding the
agent's window. A browser has no such limit. When a FastAPI route re-uses
a `cos_*` tool function to serve the SPA, it passes `apply_budget=False`
so `ok()` skips the trimmer entirely — the wire payload is bounded by the
route's own pagination, not the agent cap. This decouples the Hub wire
contract from the agent envelope: the two are different consumers of one
producer and must not share a byte budget. Without it, a large board
(≈186 KB) routed through `ok()` set `envelope_unshrinkable=True` and
logged an ERROR even though the browser could render it fine. The opt-out
is a **boolean**, not a custom byte cap — the only two states a caller
needs are "agent budget" (default) and "no budget" (browser); an
arbitrary mid-size cap has no consumer (anti-overengineering).

### Error

```json
{
  "ok": false,
  "error": {
    "category": "transient" | "validation" | "permission" | "not_found" | "unavailable" | "internal" | "module_disabled",
    "retryable": true | false,
    "message": "<human-readable>"
  }
}
```

## Error categories

| Category | When to use | `retryable` default |
|---|---|---|
| `transient` | Timeouts, connection drops, flaky downstream | `true` |
| `validation` | Bad input (wrong type, out-of-range, missing required field) | `false` |
| `permission` | Caller lacks rights (read-only DB, locked resource) | `false` |
| `not_found` | Requested entity does not exist (task_id, pattern_id) | `false` |
| `unavailable` | Optional dependency missing (embeddings not installed, FTS5 off) | `true` — user can install and retry |
| `internal` | Anything else — unexpected exception bubbled up | `false` |
| `module_disabled` | The tool's subsystem module is disabled in this project (subsystems-state.json); message names the module + `cos module enable <id>`. Emitted by the `safe_tool` gate, never by tool bodies | `false` |

If the default is wrong for a specific call, pass `retryable=` explicitly to
`fail()`.

## How to use

### Helpers

```python
# src/core/thinking_os/tools/_shared.py
from tools._shared import ok, fail, safe_tool
```

- `ok(data, *, meta=None, apply_budget=True)` → success envelope (str). `apply_budget=False` skips the token-budget trimmer for web/browser callers — see [Token budget tiers](#token-budget-tiers).
- `fail(category, message, *, retryable=None)` → error envelope (str)
- `@safe_tool` → decorator that catches common exception classes and converts
  them to `fail()` — use above each `cos_*` function body so unexpected errors
  never leak as raw tracebacks.

### Example

```python
@mcp.tool(name="cos_example", annotations={...})
@safe_tool
def cos_example(task_id: str) -> str:
    """One-line description. Returns envelope per docs/engineering/mcp-error-envelope.md."""
    if not task_id:
        return fail("validation", "task_id is required")
    row = db.lookup(task_id)
    if row is None:
        return fail("not_found", f"no task named {task_id}")
    return ok({"task_id": task_id, "status": row["status"]})
```

## Internal-error forensics (server-side log contract)

The envelope deliberately hides internals from the caller (`fail("internal",
"OperationalError: …")` is all the agent sees). The full forensic record
lives server-side, written by `@safe_tool` to the root logger — which
`server.py` attaches to `$COS_STATE_DIR/.mcp.log` (note the leading dot;
`*.log` globs miss it). Because EVERY concurrently-running MCP server
process appends to that same file, each `@safe_tool` exception log line
MUST carry enough identity to attribute the failure:

- full traceback (`logger.exception`),
- the tool name,
- the **process id** and **thread name** (multiple panels = multiple server
  processes; FastMCP runs sync tools on a threadpool),
- for `sqlite3.Error` only: a best-effort `PRAGMA database_list` snapshot
  taken from the failing connection (first positional arg when it is a
  `sqlite3.Connection`), so "which DB file was this connection actually
  attached to?" is answerable post-mortem.

Connection discipline for board mutators: the server-side wrappers obtain a
**per-thread pooled connection** (`database.get_pooled_conn`, spec:
`docs/phase-n-role-based-routing-plan.md` §7a-A) instead of sharing the
module-level startup connection across threadpool threads — cross-thread
interleaving on one `sqlite3.Connection` is undefined behaviour territory
(observed 2026-06-09: transient `no such table: tasks` under parallel tool
calls; forensics in TASK-312).

## Testing

Assertions must drill through the envelope:

```python
import json
result = server.cos_example("TASK-001")
payload = json.loads(result)
assert payload["ok"] is True
assert payload["data"]["status"] == "done"
```

For error paths:

```python
payload = json.loads(server.cos_example(""))
assert payload["ok"] is False
assert payload["error"]["category"] == "validation"
assert payload["error"]["retryable"] is False
```

## Migration status

The envelope is the contract for **all** `cos_*` tools registered in
[src/core/thinking_os/server.py](../../src/core/thinking_os/server.py). Internal helper
functions under `src/core/thinking_os/tools/*.py` still return plain Python values
(dicts/lists) — the envelope is applied only at the MCP boundary so unit tests
for helpers stay simple.

## `cos_graph_doctor` issue categories (W7.6)

`data.issues[]` carries one entry per finding. Each entry has
`category`, `count`, optional `severity` (`"real"` default, `"info"`
when the category is `informational_categories`), `sample[]`, and
sometimes a `path_count`. Categories:

| Category | Severity | What it means | `fix=True` deletes? |
|---|---|---|---|
| `dangling_source` | real | Edge with `source_id` pointing to a deleted node row | yes |
| `dangling_target` | real | Edge with `target_id` pointing to a deleted node row | yes |
| `duplicate_edges` | real | More than one row sharing `(source_id, target_id, edge_type, extractor)` | no — schema fix needed |
| `self_loops` | real | Edge with `source_id == target_id` (extractor bug) | no — fix the extractor |
| `orphaned_inrepo` | real | Node with no edges that is NOT a stub, external reference, or phantom. Real bug — most likely the symbol it referenced was deleted, or extractor over-emitted. | no — fix via reindex or by removing the dead reference |
| `orphaned_phantom` | real | Zero-edge junk the doctor can safely prune: line-anchored `task:file:` uids, `metadata.stub=true` link-target stubs whose minting edge is gone, rows whose recorded extractor id is no longer registered (extractor renames strand them — the extractor-scoped prune can never match), module/doc_external stubs with no on-disk path, extensionless file phantoms. Re-extraction re-mints any that are still referenced. | yes |
| `orphaned_external_unresolved` | **info** | `code:external:*` and `cos:identifier:*` stub surfacing — expected noise (stdlib refs, skill/adapter identifiers that don't get inbound edges by design). Never trips `healthy=false`. | no — by design |
| `malformed_uid_path` | real | Node whose `file_path` or `uid` contains `../`, backtick, or whitespace — extractor over-captured (X7 root cause: markdown link regex pulling in backticked prose). | yes |
| `stale_paths` | real | Node whose `file_path` is non-malformed but no longer exists on disk. Accumulates from file moves / deletes that idempotent-upsert reindex preserves. | yes |

The `healthy` boolean is computed by `len([i for i in issues if i.category not in informational_categories]) == 0`. So a graph with 1000 `orphaned_external_unresolved` and zero other issues reports `healthy=True`.

## EvidenceBundle (TASK-004 G3)

The `cos_supervise_record_output` tool persists per-formula-agent outputs
into a session-scoped `EvidenceBundle` (`cognition_schemas.EvidenceBundle`)
serialized as JSON under `$COS_AGENT_DIR/evidence_bundle_<session>.json`.
The bundle has one slot per role (researcher, analyst, …) plus
`backtracks`, `discoveries`, and `degraded_formulas` accumulators — see
the bundle-field registry in `cognition_schemas.py` for the
role_id → output_class mapping.

The former `exhaustive_evidence: ExhaustiveEvidence` slot, its
`validate_exhaustive_evidence` predicate check, and the completion-guardian
Stop hook were removed with the intent-enforcement layer
(ADR-0003, superseded 2026-06-08).

## Non-goals

- **Not** a general-purpose error type. Python exceptions inside helpers are
  fine; the envelope is the wire contract, not the internal one.
- **Not** i18n-aware. `message` is operator-English; agents translate for
  end-user display themselves.
- **Not** a replacement for `logger.exception()` — log and envelope are
  complementary (log for humans, envelope for agents).

## OpenAPI / typed-client mirror

The HTTP wrappers in `src/core/web/routes/**` translate the MCP envelope to the
matching HTTP shape via `_envelope.unwrap()` ([src/core/web/_envelope.py](../../src/core/web/_envelope.py)). For OpenAPI codegen the same module exposes Pydantic mirrors so generated clients (e.g. `openapi-typescript`) get typed error bodies instead of `unknown`:

```python
from web._envelope import ErrorBody, ErrorEnvelope, ENVELOPE_ERROR_RESPONSES

router = APIRouter(prefix="/api/graph", tags=["graph"],
                   responses=ENVELOPE_ERROR_RESPONSES)
```

`ENVELOPE_ERROR_RESPONSES` declares `400 / 404 / 500 / 503` with `ErrorEnvelope` as the response model — applied at router-level so every route inherits without per-route boilerplate. Routers that currently expose typed errors:

| Router | Status |
|---|---|
| `routes/board.py`, `routes/graph.py`, `routes/cognition.py`, `routes/hooks.py`, `routes/observability.py`, `routes/search.py` | ✓ documented |
| `routes/sessions.py`, `routes/presence.py`, `routes/scheduled.py`, `routes/settings.py`, `routes/hub.py`, `routes/roles.py`, `routes/stream.py` | not yet wired — defaults to FastAPI generic |

When adding a router that uses `_envelope.unwrap()`, wire `responses=ENVELOPE_ERROR_RESPONSES` to keep the typed contract complete. Regenerate `src/core/web/ui/src/lib/api-types.ts` via `npm run gen-api` (with the hub running on `:9188`) after the change.
