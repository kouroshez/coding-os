---
description: Rule for authoring or modifying MCP tools (cos_*) in src/core/thinking_os/tools/ or src/core/graph_os/tools/. Enforces envelope contract, safe-tool wrapper, one-line docstring, telemetry layer field, error categories.
globs: "src/core/thinking_os/tools/*.py,src/core/graph_os/tools/*.py,src/core/board_os/mcp_tools.py,src/core/web/routes/*.py"
alwaysApply: false
---

# MCP Tool Authoring Rule (Critical Rule 13)

The worked example, pre-edit moves, and schema traps live in `Skill mcp-tool-authoring` — load it before touching a `cos_*` tool. Contract SSOT: [docs/engineering/mcp-error-envelope.md](../../../docs/engineering/mcp-error-envelope.md) · inventory: [docs/governance/mcp-tool-inventory.md](../../../docs/governance/mcp-tool-inventory.md). Non-negotiables:

1. Every `cos_*` tool: `@safe_tool` + `@mcp.tool()`, returns `ok(data)` / `fail(category, message)` — never a hand-built dict.
2. Categories (exact strings): `validation` · `not_found` · `unavailable` (retryable) · `conflict` (retryable) · `internal`.
3. `meta.layer` required on every success (memory/docs/tasks/graph/board/cognition/metrics/learning/routing); `meta.backend_fallback=true` when a fallback answered.
4. ONE-line docstring on `@mcp.tool` functions only (FastMCP description, ends with a period); none on internal helpers (Rule 12).
5. New persistent table → append-only migration `vN+1` (Rule 9); never edit a past migration.
6. New tool → update the inventory doc.

Verify: `uv run --extra rag pytest src/core/thinking_os/tests/ -q` + `python src/core/thinking_os/server.py --test`.
