<!-- domain:META | layer:playbook | ssot:true | updated:2026-05-08 -->
# Playbook — Authoring a `cos_*` MCP Tool

> P: Step-by-step guide for adding or modifying an MCP tool exposed by `src/core/thinking_os/server.py`.
> R: Adding a new `cos_*` tool, refactoring an existing one, or auditing the contract of one that misbehaves in production.
> S: Editing pure server internals that no agent calls remotely (helpers in `_shared.py`).
> N: [docs-system.md](../governance/docs-system.md), [mcp-error-envelope.md](../engineering/mcp-error-envelope.md), [mcp-schema-traps.md](../engineering/mcp-schema-traps.md), [mcp-tool-inventory.md](../governance/mcp-tool-inventory.md)

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## When to use this playbook

Any time you Write or Edit a function decorated with `@mcp.tool` under `src/core/thinking_os/tools/`, `src/core/graph_os/tools/`, `src/core/board_os/mcp_tools.py`, or `src/core/web/routes/`. The same contract applies to all of them.

## The contract (Rule 13)

Every `cos_*` tool returns `ok(data)` or `fail(category, message)`. Internally each tool is wrapped by `@safe_tool` (defined in `src/core/thinking_os/tools/_shared.py`) which catches exceptions, normalizes the envelope, and emits a structured trace event. Bypassing `@safe_tool` is a critical bug — agents downstream parse the envelope shape, not raw return values.

## Steps

1. **Decide the surface.** A `cos_*` tool is read-only or mutating but never both. Read-only tools live under `tools/<domain>.py`. Mutating tools that touch the DB go through a workflow module (`src/core/board_os/workflow.py` is the model).
2. **Pick the file.** `src/core/thinking_os/tools/` for cognitive tools, `src/core/graph_os/tools/` for graph queries, `src/core/board_os/mcp_tools.py` for board ops. Don't open a new file unless the existing one passes 800 lines.
3. **Write the signature.** Use Pydantic models for any non-trivial input. Field names must mirror what the agent will read back — see [api-contract-discipline.md](../../src/core/rules/api-contract-discipline.md).
4. **One-line docstring.** FastMCP exposes the docstring as the tool description. One actionable sentence — what the tool does and the canonical envelope key it returns. No multi-paragraph blocks.
5. **Wrap with `@safe_tool`.** Always. Never rely on the framework's default error path.
6. **Write the unit test.** `src/core/<domain>/tests/test_<module>.py`. Test the success envelope, the failure envelope, and at least one Pydantic validation error.
7. **Run the surface test.** `make test-mcp` exercises every tool against the live registry; it must pass before merge.
8. **Update inventory.** `docs/governance/mcp-tool-inventory.md` is hand-maintained — append a row for the new tool in the same PR so the inventory stays in sync with the live registry.
9. **Update tracing if behavior is novel.** If the tool emits a new trace category, register it in `src/core/thinking_os/tracing.py`.
10. **Document a schema trap.** If the tool's input shape is non-obvious (enums, polymorphic fields, optional unions), add a row to [mcp-schema-traps.md](../engineering/mcp-schema-traps.md) with an example call. Future agents WILL guess wrong without it.

## Acceptance

- The tool returns `ok(...)` on the happy path and `fail(category, message)` on at least three error categories (validation, not_found, integrity).
- A failing call never raises through to the FastMCP transport — `@safe_tool` covers it.
- `make test-mcp` passes (runs the FastMCP self-test against the live registry).
- The tool's input shape, output keys, and trace category are documented in the appropriate reference doc.

## Rollback

A new tool is additive — revert the commit. A modified tool may have downstream callers; check `cos_graph_references(uid="code:function:<path>::<tool>")` before reverting and pin the rollback to consumers.

## Anti-patterns

- Returning a raw dict instead of the envelope. Breaks every consumer immediately.
- Hand-rolling JSON-schema for inputs. Use Pydantic — FastMCP derives the schema for free.
- Multi-paragraph docstrings. They land in agent context budgets and rarely pay rent.
- Logging via `print`. Use `cos_log_hook` or the structured logger in `_shared.py`.
- Skipping `@safe_tool` because the function "obviously won't fail." It will.
