<!-- domain:OPS | layer:reference | ssot:true | updated:2026-04-28 -->
# board_os ↔ coding-os.db Coupling Contract

Purpose: Defines the read/write contract between board_os and the shared SQLite owned by thinking_os.
Read when: Modifying board_os DB access or thinking_os tables that board_os reads.
Skip when: Pure UI / scaffold edits.
Read next: [docs-system.md](../governance/docs-system.md), [mcp-tool-inventory.md](../governance/mcp-tool-inventory.md)

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)


**Why this doc exists:** `board_os` is registered through `thinking_os/server.py` and
shares the same SQLite connection. Any schema migration or API change in either subsystem
can silently break the other. This document defines the coupling contract and the rules
that keep the two subsystems decoupled at the right abstraction layers.

---

## Coupling points

| Point | File | Nature |
|---|---|---|
| MCP registration | `core/thinking_os/server.py` | `register_board_tools(mcp, conn)` wires board_os tools onto the same MCP server instance |
| Shared connection | `core/thinking_os/server.py` | Passes the `sqlite3.Connection` from `db.init_db()` into board_os tools |
| Envelope helpers | `core/board_os/mcp_tools.py` | Imports `ok`, `fail`, `safe_tool` from `thinking_os.tools._shared` (installed package, no sys.path injection) |
| Agent detection | `core/board_os/_agent_runtime.py` | Reads `adapters/<agent>/adapter.yaml::runtime_env_markers` via `cli.adapter_registry` |
| Task doc FTS | `core/board_os/parser.py` | Uses `from thinking_os import task_parser` (installed package); bare `import task_parser` fallback for script invocation |

---

## Invariants

1. **Single DB, dual writer.** thinking_os writes to `memories`, `metrics`, `document_chunks`,
   `graph_*` tables. board_os writes to `board_tasks`, `work_log`. They MUST NOT touch each
   other's tables directly — cross-subsystem reads go through the MCP tool layer.

2. **Connection ownership.** The `sqlite3.Connection` is owned by `thinking_os/server.py`
   (created by `db.init_db`). board_os tools receive it as an argument and MUST NOT call
   `conn.close()` or change the journal mode.

3. **Schema migrations are append-only (Rule 9).** New tables for board_os get a migration
   version ≥ current thinking_os migration count. Never edit past migrations.

4. **Envelope contract (Rule 14).** All board_os MCP tools MUST use `ok(data)` / `fail(category, msg)`
   from `core/thinking_os/tools/_shared.py`. Never return raw dicts.

5. **agent-detection SSOT.** `core/board_os/_agent_runtime.py::detect_agent()` is the single
   source of truth. The MCP tool `_agent_label()` must delegate to it, not re-implement.

---

## Adding a new board_os MCP tool

1. Add the function to `core/board_os/mcp_tools.py`.
2. Decorate with `@safe_tool` (imported from `_shared`).
3. Register via `register_board_tools` — no new `@mcp.tool()` decorators outside this function.
4. Follow the `PURPOSE / INPUT / OUTPUT / DEPENDENCIES / NOTES` docstring convention (Rule 12).
5. Add to `docs/governance/mcp-tool-inventory.md` if it modifies state.

---

## DB schema split

```
thinking_os tables:
  memories, memory_edits, metrics, learning_events,
  document_chunks, document_chunks_fts,
  roles, personas, formulas,
  graph_nodes, graph_edges_v12, graph_evidence_v12
  (all managed by core/thinking_os/database.py migrations)

board_os tables:
  board_tasks, work_log
  (added by db.py migrations >= v8, owned by board_os)
```

---

## Testing the coupling

```bash
# board_os unit tests (use the same in-memory db as thinking_os tests)
uv run --extra rag --with aiohttp --with pytest-asyncio pytest core/board_os/tests/ -q

# Verify MCP server boots with both subsystems registered
python core/thinking_os/server.py --test
```

---

*This document is a governance artifact — AGENTS.md Rule 19 applies: keep it in sync
when coupling points change. See also [mcp-tool-inventory.md](../governance/mcp-tool-inventory.md).*
