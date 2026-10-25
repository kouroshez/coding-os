---
id: TASK-1082
title: "Graph: typed-receiver calls, core.-prefixed facades, registered symbols in dead_code, scoped hooks, stub and stale flags"
swimlane: "graph_os"
kind: bug
epic: null
labels: [docs-update, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-10-25
started: 2026-10-25
completed: 2026-10-25
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1082: Graph: typed-receiver calls, core.-prefixed facades, registered symbols in dead_code, scoped hooks, stub and stale flags

**Outcome (one sentence):** Six graph answers that misled agents are corrected: method calls through typed variables reach the method, core.-prefixed facade calls reach the definition, dead_code stops listing framework-registered commands/routes/properties, adapter-scoped hooks declare their real script, resolve never returns a stub as a certain file, and search/resolve flag results from files that changed or vanished since indexing.

## Read First
- docs/engineering/graph_os-queries.md
- src/core/graph_os/extractors/_python_resolve.py
- src/core/graph_os/backends/_sqlite_links.py
- src/core/graph_os/tools/_graph_hygiene.py

## Repro Steps
references(_SqliteReadMixin.get_node) and GraphBackend.get_node returned 0 while rg finds 21 call sites (edges went to code:external:unresolved:backend.get_node); references(_decode_board_cursor) returned 2 and missed 3 mcp_tools._decode_board_cursor test calls; dead_code(kind=function) listed ~90 click commands and @property methods; resolve('sync-agent-memory.sh') returned a stub with confidence 1.0; search returned deleted tests with no freshness signal.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `def f(backend: GraphBackend)` or `x = Klass()`, **When** the file is extracted, **Then** `backend.m()` / `x.m()` emits a calls edge at 0.8 to `Klass.m`, and a name bound to two classes stays unresolved.
- **Given** a stub `core.pkg.mod:name` whose module is indexed as `pkg.mod`, **When** link_external_stubs runs, **Then** it reaches the defining function through the facade, and `django.db.models` never binds a local `db/models.py`.
- **Given** dead_code, **When** a symbol carries a registering decorator (command, route, tool, fixture, property), **Then** it is not listed, while a wrapper decorator like lru_cache changes nothing.
- **Given** an adapter_scope hook, **When** registry.yaml is extracted, **Then** its declares edge targets src/adapters/<scope>/hooks/<script> independent of the process cwd.
- **Given** resolve or search, **When** a hit is a stub or comes from a changed or deleted file, **Then** it carries stub/stale flags and a stub never wins path_resolve.

## Work Log
- 2026-10-25 [claude]: Each finding from the read-only audit agent was reproduced by me before fixing (references/resolve/dead_code/DB…
- 2026-10-25 [claude]: Status transitioned to complete via cos task-done.
