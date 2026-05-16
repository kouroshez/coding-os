<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-05-13 -->
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
  "data": <T>
}
```

`data` is whatever the tool produced — a dict, a list, a scalar, or even
`null`. Consumers should drill through `data` rather than the top level.

### Error

```json
{
  "ok": false,
  "error": {
    "category": "transient" | "validation" | "permission" | "not_found" | "unavailable" | "internal",
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

If the default is wrong for a specific call, pass `retryable=` explicitly to
`fail()`.

## How to use

### Helpers

```python
# src/core/thinking_os/tools/_shared.py
from tools._shared import ok, fail, safe_tool
```

- `ok(data)` → success envelope (str)
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
