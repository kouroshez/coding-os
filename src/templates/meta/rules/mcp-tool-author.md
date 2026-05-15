---
description: Rule for authoring or modifying MCP tools (cos_*) in src/core/thinking_os/tools/ or src/core/graph_os/tools/. Enforces envelope contract, safe-tool wrapper, one-line docstring, telemetry layer field, error categories.
globs: "src/core/thinking_os/tools/*.py,src/core/graph_os/tools/*.py,src/core/board_os/mcp_tools.py,src/core/web/routes/*.py"
alwaysApply: false
---

# MCP Tool Authoring Rule (Critical Rule 13)

Source of truth: [docs/engineering/mcp-error-envelope.md](../../../docs/engineering/mcp-error-envelope.md).
Inventory: [docs/governance/mcp-tool-inventory.md](../../../docs/governance/mcp-tool-inventory.md).

## Envelope contract — non-negotiable

Every `cos_*` tool returns either:

```python
{"ok": True,  "data": <payload>, "meta": {"layer": "<layer>", ...}}
{"ok": False, "error": {"category": "<cat>", "message": "<human>", "retryable": <bool>}}
```

Use the `@safe_tool` decorator from `src/core/thinking_os/tools/_shared.py`.
It auto-wraps exceptions into `fail("internal", str(exc))`.

```python
from thinking_os.tools._shared import safe_tool, ok, fail

@safe_tool
@mcp.tool()
def cos_my_new_tool(arg: str) -> dict:
    """One-line description — shown by FastMCP to the agent."""
    if not arg:
        return fail("validation", "arg must be non-empty")
    result = compute(arg)
    return ok({"result": result, "meta": {"layer": "thinking_os"}})
```

## Categories (use these exact strings)

| Category | Meaning |
|---|---|
| `validation` | Caller passed bad arguments. Not retryable. |
| `not_found` | Resource doesn't exist. Not retryable. |
| `unavailable` | Backend offline (Kùzu, embedding model). Retryable. |
| `conflict` | State race / concurrent edit. Retryable after read. |
| `internal` | Unhandled exception (set by `@safe_tool`). Not retryable. |

## Telemetry — `meta.layer` is required

Every successful response carries `meta.layer` so the agent (and tests)
know which retrieval layer answered. Layers: `memory`, `docs`, `tasks`,
`graph`, `board`, `cognition`, `metrics`, `learning`, `routing`, `audit`.

When the answer was a fallback (e.g. SQLite responded because Kùzu was
offline), set `meta.backend_fallback=true`.

## Docstring rule (Rule 12)

ONE-line docstring on `@mcp.tool` functions. FastMCP exposes that line as
the tool's description to the agent — it must be self-explanatory and
end with a period. NO multi-paragraph docstrings on internal helpers.

## Schema migrations (Rule 9)

Adding a new persistent table → write `src/core/thinking_os/migrations/vN+1_<name>.sql`.
Never edit a previous migration. Tests in `src/core/thinking_os/tests/test_db.py`
guard the append-only invariant.

## Pre-edit moves

1. `cos_graph_context("src/core/thinking_os/tools/<file>.py", depth=1)` — see neighbours.
2. `cos_graph_references("cos_<existing_tool>")` — find consumers if you're modifying signature.
3. Read [docs/engineering/mcp-error-envelope.md](../../../docs/engineering/mcp-error-envelope.md) — the contract.
4. Update [docs/governance/mcp-tool-inventory.md](../../../docs/governance/mcp-tool-inventory.md) when adding a new tool.

## Verification

- `uv run --extra rag pytest src/core/thinking_os/tests/ -q`
- `python src/core/thinking_os/server.py --test` (MCP self-test)
- Call the new tool via the running MCP server to confirm registration.
