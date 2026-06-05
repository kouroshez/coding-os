<!-- domain:META | layer:asset | ssot:false | updated:2026-06-04 -->
# Meta-Server Python Checklist

Run when editing Python in the kernel (thinking_os / graph_os / board_os / hooks helpers / cli).

## Envelope + tools (Rule 13/2/12)
- [ ] Every `@mcp.tool()` also `@safe_tool`; returns `ok()`/`fail()`.
- [ ] Tool name `cos_`-prefixed; one-line docstring only (it's the agent description).
- [ ] `python3 scripts/check_envelope.py <tools file>` → `clean`.

## Types + style
- [ ] Type hints on every function signature (params + return).
- [ ] `from __future__ import annotations` at the top of new modules.
- [ ] Internal helpers have NO docstrings (Rule 12); comments by exception.
- [ ] Fire-and-forget wrapped in `_*_safe()` with `except Exception as exc: logger.debug(...)` (Rule 6).
- [ ] `Path(...).resolve()` before `.relative_to()` (Rule 5).

## Schema (Rule 9)
- [ ] New persistent table → `migrations/vN+1_<name>.sql` (append-only); no past migration edited.

## Multi-step verification (Rule 8)
- [ ] No bash heredoc inside `uv run` — extract to a Python helper.

## Verify (matrix-targeted)
- [ ] thinking_os → `uv run --extra rag pytest src/core/thinking_os/tests/ -q` + server `--test`.
- [ ] graph_os → `uv run --extra graph_os pytest src/core/graph_os/tests/ -q`.
- [ ] board_os → `uv run --extra rag --with aiohttp --with pytest-asyncio pytest src/core/board_os/tests/ -q`.
- [ ] cli → `uv run pytest tests/test_cli.py -q`.
