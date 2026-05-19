---
name: python-meta-server
description: Use when authoring or modifying Python code in the meta-repo's server / kernel — MCP tools (src/core/thinking_os/), graph extractors (src/core/graph_os/), board engine (src/core/board_os/), hooks helpers (src/core/hooks/_helpers/), and CLI (cli/). Codifies the FastMCP envelope contract, type-hint discipline, async patterns, exception hierarchy, and the regen pipelines specific to this codebase. Pairs with graph-explorer (always primary), meta-engineering, and clean-code.
last_reviewed: "2026-05-11"

---

# python-meta-server

Purpose: Internalise the Python authoring conventions that make this
meta-repo work — MCP envelope, FastMCP registration, schema migrations,
extractor idempotency, hook helper structure. Without this skill,
agents write Python that LOOKS correct but breaks the contracts that
every consumer project depends on.

Read when: editing any of:
- `src/core/thinking_os/**/*.py` — MCP server, tools, dispatcher, cognition.
- `src/core/graph_os/**/*.py` — backends, extractors, ingestion.
- `src/core/board_os/**/*.py` — Scrumban engine.
- `src/core/hooks/_helpers/**/*.py` — hook helpers.
- `src/cli/**/*.py` — factory CLI.
- `src/core/web/server.py`, `src/core/web/routes/**/*.py` — FastAPI routes.

Skip when: editing tests (`*test*.py`), scripts (`scripts/`), or one-off helpers.

## Hard contracts

### 1. MCP envelope — Rule 13 (NON-NEGOTIABLE)

Every `cos_*` MCP tool returns either:

```python
{"ok": True,  "data": <payload>, "meta": {"layer": "<layer>", ...}}
{"ok": False, "error": {"category": "<cat>", "message": "<human>", "retryable": <bool>}}
```

Use `@safe_tool` from `src/core/thinking_os/tools/_shared.py`:

```python
from thinking_os.tools._shared import safe_tool, ok, fail

@safe_tool
@mcp.tool()
def cos_my_tool(arg: str) -> dict:
    """One-line description for FastMCP."""  # ← Rule 12
    if not arg:
        return fail("validation", "arg must be non-empty")
    return ok({"result": ...}, meta={"layer": "thinking_os"})
```

Categories: `validation` · `not_found` · `unavailable` (retryable) · `conflict` (retryable) · `internal`.

### 2. Docstrings — Rule 12

ONE-line docstring on `@mcp.tool` functions only — FastMCP exposes
that line as the agent-facing description. NO multi-line docstrings on
internal helpers. Comments by exception, not by default.

### 3. Schema migrations — Rule 9

Adding a persistent table: write `src/core/thinking_os/migrations/vN+1_<name>.sql`.
NEVER edit a previous migration. `tests/test_db.py` guards the invariant.

### 4. Extractor idempotency

Every graph extractor:
- Keys nodes by stable `uid` (e.g. `code:function:<path>::<name>`).
- Short-circuits via `file_index_state` content_hash when the file's
  hash matches the last extraction.
- Never returns duplicate uids in one batch.

### 5. Async + FastMCP

MCP tool functions can be sync OR async. If async, do NOT block the
event loop with sync I/O — wrap in `asyncio.to_thread` or use
`anyio.to_thread.run_sync`.

### 6. CLI no-hardcode (Rule 11)

`src/cli/**/*.py` MUST NOT hardcode stack/adapter literals. Discover via:
- `cli.adapter_registry.load_adapter_registry()`
- `cli.stack_registry.load_stack_registry()`

Tests `tests/test_no_hardcoded_anthropic.py` + `tests/test_no_hardcoded_stacks.py` enforce.

## Pre-edit moves

1. `cos_graph_resolve("the function I want to edit")` → canonical uid.
2. `cos_graph_context(uid, depth=1)` → neighbours + types + decorators.
3. `cos_graph_references(uid)` → who calls / depends on it.
4. For signature change: `cos_graph_impact(uid, direction="downstream", depth=3)`.
5. For rename: `cos_graph_rename_plan(uid, new_name)`.
6. THEN Read the file (max 1).

## Common patterns

### Defensive imports for optional deps

```python
try:
    import sentence_transformers
    _HAS_EMBEDDINGS = True
except ImportError:
    _HAS_EMBEDDINGS = False
```

### Telemetry without blocking

```python
def _emit(meta: dict) -> None:
    try:
        with open(path, "a") as f:
            f.write(json.dumps(...) + "\n")
    except OSError as exc:
        logger.debug("telemetry skipped: %s", exc)  # fail-open
```

### Path resolution (Rule 5 — macOS quirk)

```python
# /tmp ↔ /private/tmp on macOS — always resolve before relative_to
real = Path(p).resolve()
rel = real.relative_to(REPO_ROOT.resolve())
```

## Anti-patterns

- **Multi-paragraph docstrings on internal helpers** — Rule 12 violation.
- **Direct sqlite3 in tool layer** — must go through `GraphBackend` interface.
- **Editing previous migration** — Rule 9 violation; new tables → vN+1.
- **Bare `except Exception` without logging** — fail-open helpers must log at debug.
- **Importing from `adapters/` inside `core/`** — P8 violation (Adapter-SDK autonomy).
- **Hardcoding `.claude/` literal** — P2 violation; use `$COS_AGENT_DIR` env var.

## Verification matrix

| Changed | Command |
|---|---|
| `src/core/thinking_os/**` | `uv run --extra rag pytest src/core/thinking_os/tests/ -q` + `python src/core/thinking_os/server.py --test` |
| `src/core/graph_os/**` | `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` |
| `src/core/board_os/**` | `uv run --extra rag --with aiohttp --with pytest-asyncio pytest src/core/board_os/tests/ -q` |
| `src/cli/**` | `uv run pytest tests/test_cli.py -q` |
| `src/core/web/**` | hub smoke + the relevant test_* in tests/ |
| Schema migration | `uv run --extra rag pytest src/core/thinking_os/tests/test_db.py -q` |

NEVER run `pytest tests/ -q` mid-task — that's the 6-minute full-sweep gate, pre-merge only.

## See also

- [docs/engineering/mcp-error-envelope.md](../../../../docs/engineering/mcp-error-envelope.md)
- [docs/engineering/graph_os-queries.md](../../../../docs/engineering/graph_os-queries.md)
- [docs/governance/critical-rules.md](../../../../docs/governance/critical-rules.md)
- [src/templates/meta/rules/mcp-tool-author.md](../../rules/mcp-tool-author.md)
- [src/templates/meta/rules/hook-author.md](../../rules/hook-author.md)
