---
id: TASK-843
title: "Full graph-reindex reconcile misses folder-spine + phantom ghosts (residue never self-heals)"
swimlane: "graph_os"
kind: bug
epic: null
labels: [graph, reindex, reconcile, self-healing, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-07-17
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-843: Full graph-reindex reconcile misses folder-spine + phantom ghosts (residue never self-heals)

**Outcome (one sentence):** A full uncapped `cos graph-reindex` self-heals ALL graph residue — folder-spine nodes and zero-edge phantoms left by bulk directory moves/deletes (git mv / rm -rf), not just the file nodes tracked in file_index_state — so graph health stays green without a manual `cos_graph_doctor --fix`.

## Read First
- src/cli/graph_commands.py
- src/core/graph_os/tools/graph.py
- src/core/graph_os/tools/reindex_dispatch.py

## Repro Steps
The `core/`→`src/core/` and `adapters/`→`src/adapters/` reorg (plus deleted dirs e.g. adapters/cursor) left 73 folder-spine ghosts + 106 phantom orphans. The full-reindex reconcile at src/cli/graph_commands.py:738 reads only `SELECT DISTINCT file_path FROM file_index_state`, which holds file rows only — folder-spine and NULL-path phantom nodes are never in that set, so they survive every full reindex and cos_graph_doctor stays health=attention.

## Acceptance (G/W/T) — *this IS the Definition of Done*
G/W/T:
- Given a graph carrying folder-spine ghosts (folder path absent on disk) and zero-edge phantoms after a `core/`→`src/core/` style reorg, When a full uncapped `cos graph-reindex` completes, Then those residual nodes are pruned and `cos_graph_doctor` reports healthy=true (issue_count=0).
- Given a `--path` sub-walk or a max_files-capped walk, When it completes, Then the residue sweep does NOT run (no false prune of un-walked but on-disk files) — same guard as the existing file reconcile.
- Given live `src/`-prefixed folder nodes with contains edges, When the sweep runs, Then they are NOT deleted (stale-delete skips existing paths; phantom-delete skips edged nodes).

## Work Log
- 2026-07-17 [claude]: Deliberation: reused cos_graph_doctor(fix=True) inside the existing full-walk reconcile (placed AFTER the global…
- 2026-07-17 [claude]: Implemented + verified. Added residue-sweep (reuse cos_graph_doctor safe-repair) after global link in the full-walk…
