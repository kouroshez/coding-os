"""graph_os MCP tool modules.

Each module registers a `cos_graph_*` tool in the shared MCP server
(`core/thinking_os/server.py`). Every tool returns through the
`ok(data, meta=...)` / `fail(category, message)` envelope defined in
`docs/engineering/mcp-error-envelope.md`; `data.meta.layer="graph"` is
always set so agents can route responses through the three-layer
retrieval model (CLAUDE.md Three-Layer Retrieval).
"""
