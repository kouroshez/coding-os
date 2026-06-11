---
name: mcp-tool-authoring
tier: stack
domain: [architecture]
description: Author production-grade MCP (Model Context Protocol) tools for the coding-os meta-repo. Use when adding a new `cos_*` tool to `src/core/thinking_os/tools/`, `src/core/graph_os/tools/`, `src/core/board_os/mcp_tools.py`, or `src/core/web/routes/` — the four canonical authoring surfaces. Enforces the @safe_tool envelope (Rule 13), name prefix `cos_` (Rule 2), append-only schema migrations (Rule 9), single-line docstring (Rule 12), deferred-tool schema discipline. Pairs with python-meta-server, graph-explorer (load before edits), and clean-code.
last_reviewed: "2026-05-11"
---

# mcp-tool-authoring

Purpose: Make every new `cos_*` MCP tool match the contract every other tool follows. Drift here breaks the agent (deferred-tool schema lookups), the envelope (Rule 13), or the migration (Rule 9). One canonical authoring path keeps the ~80 tools coherent.

Read when: editing files matching:
- `src/core/thinking_os/tools/*.py` — MCP tools registered with the FastMCP server.
- `src/core/graph_os/tools/*.py` — graph-side tools (`cos_graph_*`).
- `src/core/board_os/mcp_tools.py` — Scrumban / task tools.
- `src/core/web/routes/*.py` — HTTP routes that wrap an MCP tool for the Hub UI.
- `src/core/thinking_os/server.py` — when registering a new tool module.

Skip when: editing tests, helpers, or non-tool internals.

## The Five Hard Contracts

Every `cos_*` tool MUST satisfy ALL of:

### 1. Name prefix `cos_` (Rule 2)

```python
@mcp.tool
@safe_tool
async def cos_search(query: str, limit: int = 5) -> dict:
    ...
```

Names without the `cos_` prefix are silently rejected from the tool inventory. The inventory is the SSOT for `docs/governance/mcp-tool-inventory.md` (regenerated, not hand-edited).

### 2. Envelope shape via `@safe_tool` (Rule 13)

Every tool returns `ok(data)` or `fail(category, message)`. The decorator does this for you:

```python
from core.thinking_os.tools._shared import safe_tool, ok, fail

@mcp.tool
@safe_tool  # converts raw exceptions to fail() envelopes
async def cos_search(query: str, limit: int = 5) -> dict:
    if not query:
        return fail("invalid_input", "query is required")

    rows = await _db.search(query, limit=limit)
    return ok({"results": rows, "count": len(rows), "meta": {"layer": "memory"}})
```

`fail` categories are documented in [docs/engineering/mcp-error-envelope.md](../../../docs/engineering/mcp-error-envelope.md): `invalid_input`, `not_found`, `unavailable`, `permission_denied`, `internal_error`, `rate_limited`. Don't invent new categories without updating the contract doc.

### 3. ONE-line docstring (Rule 12)

The docstring becomes the FastMCP tool description shown to the agent. It's the agent's only hint about what the tool does. Format:

```python
@mcp.tool
@safe_tool
async def cos_search(query: str, limit: int = 5) -> dict:
    """Search agent memory + learned patterns. Returns top-K ranked observations."""
    ...
```

**No docstrings on internal helpers** (Rule 12). Internal helpers are private and self-documenting via naming.

The description body (visible via `ToolSearch` lookup) can be richer — it's the docstring extended in the `description=` argument of `@mcp.tool(description=...)` if you need more than one line.

### 4. Append-only schema (Rule 9)

If your tool reads/writes the DB and needs a new table or column:

- Migrations live as **callable functions in [src/core/thinking_os/database.py](../../../core/thinking_os/database.py)** (the `MIGRATIONS` list), not standalone `.sql` files. Append a new entry at the end of the list — never edit or reorder past entries.
- **Adding a column to an existing table** → also a new migration entry (`ALTER TABLE ... ADD COLUMN ... NULL`). Backfill in a separate migration if non-trivial.
- The migration runner (`run_migrations` in `database.py`) is idempotent by `schema_version` row; each entry runs at most once per DB.

Verify with `uv run --extra rag pytest src/core/thinking_os/tests/test_db.py -q`.

### 5. Type hints, no `Any` for tool args

FastMCP introspects type hints to generate the JSON schema agents use. `Any` defeats this. Required:

```python
async def cos_doc_search(
    query: str,
    source_types: str = "",  # CSV, not list — FastMCP nested-array trap
    limit: int = 5,
    mode: str = "auto",       # "auto" | "semantic" | "lexical"
) -> dict:
    ...
```

**Schema traps** (the ones every author trips):

| Trap | Wrong | Right |
|---|---|---|
| List args break across runtimes | `tags: list[str]` | `tags_csv: str = ""` then split server-side |
| Optional list | `tags: list[str] \| None = None` | `tags_csv: str = ""` |
| TaskSignals dict field types | mixed-type dicts | `dict[str, str]` and parse server-side |
| Pydantic model arg | `task: Task` | flat primitives, construct server-side |

See [docs/engineering/mcp-schema-traps.md](../../../docs/engineering/mcp-schema-traps.md) for the live list.

## Authoring Steps (in order)

### Step 1 — graph-first

```bash
# Find related tools
cos_graph_query "search OR retrieval"

# Read the neighborhood of a similar tool you'd model on
cos_graph_context "code:function:src/core/thinking_os/tools/memory.py::cos_search" depth=1

# Confirm no name collision
cos_graph_references "cos_search"  # in case you're tempted to reuse a name
```

### Step 2 — doc-first (Rule 19)

Add the tool to its inventory section in `docs/governance/mcp-tool-inventory.md` **before** writing code. Inventory entry shape:

```markdown
### `cos_my_new_tool`
- **Category:** memory | retrieval | tasks | graph | cognition | observability | audit
- **Purpose:** One-sentence what it does.
- **Args:** `arg1: type — description. arg2: type — description (default).`
- **Returns:** `ok({data shape})` / `fail(category, message)`.
- **Source:** [`src/core/thinking_os/tools/<module>.py::cos_my_new_tool`](../../core/thinking_os/tools/<module>.py)
```

The doc is the contract. The code below implements it.

### Step 3 — choose the home module

| Concern | Module |
|---|---|
| Agent memory / learning | `src/core/thinking_os/tools/memory.py` |
| Metrics / observability of agent | `src/core/thinking_os/tools/metrics.py` |
| Doc / RAG retrieval | `src/core/thinking_os/tools/docs.py` |
| Tasks / Scrumban | `src/core/board_os/mcp_tools.py` |
| Knowledge graph queries | `src/core/graph_os/tools/<name>.py` |
| Routing / classification / cognition | `src/core/thinking_os/tools/routing.py` / `cognition.py` |
| Hub HTTP wrapper | `src/core/web/routes/<name>.py` |

If your tool spans concerns, prefer the most specific module + use cross-imports — don't create a new module unless ≥3 tools justify it.

### Step 4 — register the tool

The MCP server registers tool modules in [src/core/thinking_os/server.py](../../../core/thinking_os/server.py). New module = new `import_module` call in the registration list.

### Step 5 — write the tool

```python
# src/core/thinking_os/tools/my_module.py
from __future__ import annotations

from core.thinking_os.tools._shared import fail, ok, safe_tool


async def cos_my_new_tool(query: str, limit: int = 5) -> dict:
    """One-line description shown to the agent."""
    if not query or len(query) > 1024:
        return fail("invalid_input", "query must be 1..1024 chars")

    rows = await _do_the_work(query, limit)
    return ok({
        "results": rows,
        "count": len(rows),
        "meta": {
            "layer": "memory",  # or "docs" / "tasks" / "graph"
            "source": "thinking_os.my_new_tool",
            "tokens_estimated": _estimate_tokens(rows),
            "truncated": len(rows) >= limit,
        },
    })


async def _do_the_work(query: str, limit: int) -> list[dict]:
    # Private helper — no docstring.
    ...


def register(mcp) -> None:
    """Called by server.py during startup."""
    mcp.tool(safe_tool(cos_my_new_tool))
```

### Step 6 — tests

Three tests minimum per tool:

```python
# src/core/thinking_os/tests/test_my_module.py
import pytest

async def test_cos_my_new_tool_returns_envelope_on_success() -> None:
    result = await cos_my_new_tool(query="test")
    assert result["ok"]
    assert "results" in result["data"]
    assert "meta" in result["data"]


async def test_cos_my_new_tool_rejects_empty_query() -> None:
    result = await cos_my_new_tool(query="")
    assert not result["ok"]
    assert result["error"]["category"] == "invalid_input"


async def test_cos_my_new_tool_rejects_oversize_query() -> None:
    result = await cos_my_new_tool(query="x" * 2000)
    assert not result["ok"]
    assert result["error"]["category"] == "invalid_input"
```

Matrix command: `uv run --extra rag pytest src/core/thinking_os/tests/test_my_module.py -q`.

### Step 7 — regen + smoke

```bash
# Regenerate the public tool inventory
make regen-rules

# Re-run MCP server self-test (instantiates server, asserts all tools registered)
python src/core/thinking_os/server.py --test

# Run the matrix command for the module you edited
uv run --extra rag pytest src/core/thinking_os/tests/ -q
```

## Deferred-Tool Schema (Claude-specific)

All ~80 `cos_*` tools are **deferred** in the Claude adapter — schemas are NOT loaded at session start. Calling a tool the first time in a session requires:

```
ToolSearch("select:cos_my_new_tool")
```

This is a runtime concern, not an authoring one — but you should know that adding a tool also means the agent will need a ToolSearch call to use it for the first time per session. The docstring is the tool's only "before-Schema-Load" identifier.

## Meta-tool patterns

| Pattern | Example | When to use |
|---|---|---|
| **Search** | `cos_search`, `cos_doc_search` | Returning ranked rows from one layer |
| **Get-by-id / get-detail** | `cos_details`, `cos_doc_header` | Single-object fetch |
| **Mutation** | `cos_observation_record`, `cos_task_create` | Creates a row, returns id |
| **Action** | `cos_task_move`, `cos_supervise` | Side-effecting state change |
| **Aggregate / query** | `cos_metric_query`, `cos_log_query` | Filter + group, no mutation |
| **Composite / router** | `cos_route_skill`, `cos_classify_prompt` | Dispatches/classifies by signal |

When in doubt, model your tool on the closest existing one.

## Anti-patterns (reject in review)

- **Tool without `@safe_tool`** — raw exceptions reach the agent, not the envelope.
- **Tool name not prefixed `cos_`** — silently dropped from inventory.
- **Multi-line docstring** — clutters FastMCP description, breaks Rule 12.
- **Editing a past migration** — Rule 9 violation. New migration only.
- **`Any` type hints** — defeats schema generation.
- **List-typed args** — schema flakiness across runtimes; use CSV strings.
- **`print` in tool body** — pollutes MCP stderr. Use `logger`.
- **Returning a string instead of `ok(data)`** — every consumer expects the envelope.
- **Side effects in a "search" tool** — search/get must be read-only. Use a mutation tool for writes.
- **Tool that requires the client to know an internal id** — return resolvable identifiers (paths, uids, slugs), not row PKs.

## Verification (after authoring)

```bash
# Single-tool test
uv run --extra rag pytest src/core/thinking_os/tests/test_<your_module>.py -q

# Module-level
uv run --extra rag pytest src/core/thinking_os/tests/ -q

# MCP self-test (registers + validates all tools)
python src/core/thinking_os/server.py --test

# Regen inventory
make regen-rules
```

Pre-merge: also `make verify` (full sweep).

## Tooling

Scaffold a compliant `cos_*` tool stub (cos_ prefix, @safe_tool, ok/fail, one-line docstring):
`python3 scripts/new_tool.py --name widget --layer graph`

## See also

- [assets/mcp-tool-checklist.md](assets/mcp-tool-checklist.md) — the authoring + registration gate.
- [Rule 13 — MCP Envelope](../../../docs/governance/critical-rules.md#rule-13--mcp-tool-response-envelope)
- [MCP Error Envelope contract](../../../docs/engineering/mcp-error-envelope.md)
- [MCP Tool Inventory (SSOT)](../../../docs/governance/mcp-tool-inventory.md)
- [MCP Schema Traps](../../../docs/engineering/mcp-schema-traps.md)
- [python-meta-server](../python-meta-server/SKILL.md) — Python authoring conventions for this codebase.
- [graph-explorer](../../../core/skills/graph-explorer/SKILL.md) — pre-edit graph context.
