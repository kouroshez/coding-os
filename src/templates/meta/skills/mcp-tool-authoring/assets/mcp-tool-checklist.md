<!-- domain:META | layer:asset | ssot:false | updated:2026-06-04 -->
# MCP Tool Authoring Checklist

Run before shipping a new `cos_*` tool. Full procedure: docs/playbooks/mcp-tool-authoring.md.

## Contract
- [ ] Name prefixed `cos_` (Rule 2).
- [ ] Wrapped with `@safe_tool`; returns `ok(data)` / `fail(category, message)` (Rule 13).
- [ ] `fail` category ∈ validation / not_found / unavailable / conflict / internal.
- [ ] One-line docstring ending in a period (Rule 12) — it's the agent-facing description.
- [ ] `meta.layer` set on success; `meta.backend_fallback=true` when a fallback answered.
- [ ] `bash scripts/new_tool.py --name <t> --layer <l>` used (or matches its shape).

## Schema (if persistent state)
- [ ] New table → `src/core/thinking_os/migrations/vN+1_<name>.sql` (append-only, Rule 9).
- [ ] Never edited a past migration.

## Pre-edit graph moves
- [ ] `cos_graph_context` on the target tools file (depth=1).
- [ ] `cos_graph_references` if changing an existing tool's signature.

## Register + document
- [ ] Tool importable + registered on the MCP server.
- [ ] `docs/governance/mcp-tool-inventory.md` updated with the new tool.
- [ ] Deferred-schema note: callers run `ToolSearch("select:<tool>")` before first use.

## Verify
- [ ] `uv run --extra rag pytest src/core/thinking_os/tests/ -q`.
- [ ] `python src/core/thinking_os/server.py --test` (MCP self-test).
