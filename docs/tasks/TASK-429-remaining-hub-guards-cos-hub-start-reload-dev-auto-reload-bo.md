---
id: TASK-429
title: "Remaining Hub guards: cos hub start --reload (dev auto-reload) + bounded init graph-build (no empty graph on big repos)"
swimlane: infra
kind: feature
epic: null
labels: [hub, graph, consumer-ux, dev-loop, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-15
started: 2026-06-15
completed: 2026-06-15
agent_session: ses-claude-20260615-012959-d18c
depends_on: []
blocked_by: []
references: []
---
# TASK-429: Remaining Hub guards: cos hub start --reload (dev auto-reload) + bounded init graph-build (no empty graph on big repos)

**Outcome (one sentence):** Close the last two consumer/dev breakage seams from the graph-staleness investigation. (1) `cos hub start --reload` runs uvicorn with reload scoped to core_dir() so a meta-dev's core edits go live with no manual restart; reload mode suppresses the hub.code_fresh staleness signal (reload keeps it fresh) so status/doctor/update never false-positive. (2) `_initial_graph_index` gets a bounded timeout (COS_INIT_GRAPH_TIMEOUT, default 180s) and the Hub Composer's cos-init subprocess gets headroom, so a large new repo degrades to a gracefully-empty graph + `cos graph-reindex` HINT instead of hard-failing init at the 180s wall.

## Read First
- src/cli/hub_commands.py
- src/core/web/server.py
- src/cli/main.py
- src/core/web/routes/hub.py
- docs/engineering/hub-architecture.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `cos hub start --reload` **When** a file under src/core changes **Then** uvicorn auto-restarts the worker (reload_dirs scoped to core_dir) and `cos hub status`/`cos doctor` report PASS (no stale warning) because a reload marker suppresses the signal. - **Given** a non-reload hub **When** core changes after start **Then** the staleness signal still fires (regression guard for TASK-428). - **Given** `cos init` on a repo whose graph build exceeds the timeout **When** the bounded `_initial_graph_index` times out **Then** init still completes, prints a WARN + `cos graph-reindex` HINT, and leaves an empty (not errored) graph. - **Given** the Hub Composer create path **When** init runs **Then** its subprocess timeout has headroom over the graph-build cap so a slow build never truncates a half-created project.

## Work Log
- 2026-06-15 [claude]: Edit hub-architecture.md
- 2026-06-15 [claude]: Edit hub-architecture.md
- 2026-06-15 [claude]: Edit hub-architecture.md
- 2026-06-15 [claude]: Edit hub_commands.py
- 2026-06-15 [claude]: Edit hub_commands.py
- 2026-06-15 [claude]: Edit hub_commands.py
- 2026-06-15 [claude]: Edit hub_commands.py
- 2026-06-15 [claude]: Edit hub_commands.py
- 2026-06-15 [claude]: Edit hub_commands.py
- 2026-06-15 [claude]: Edit server.py
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit test_init_graph_index.py
- 2026-06-15 [claude]: Edit test_hub_staleness.py
- 2026-06-15 [claude]: Edit test_hub_staleness.py
- 2026-06-15 [claude]: Edit test_init_graph_index.py
- 2026-06-15 [claude]: Edit test_init_graph_index.py
- 2026-06-15 [claude]: Shipped both remaining guards. (1) `cos hub start --reload`: uvicorn reload scoped to core_dir (reload_dirs), hub.reload
- 2026-06-15 [claude]: Status transitioned to complete via cos task-done.
