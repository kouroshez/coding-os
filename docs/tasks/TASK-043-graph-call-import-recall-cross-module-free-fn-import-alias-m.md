---
id: TASK-043
title: "graph call/import recall: cross-module free-fn import-alias + module-uid dedup (recall 11-17%)"
swimlane: infra
kind: bug
epic: null
labels: []
status: icebox
priority: P1
appetite: "1d"
created: 2026-05-29
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-043: graph call/import recall: cross-module free-fn import-alias + module-uid dedup (recall 11-17%)

**Outcome (one sentence):** cos_graph_references/impact/rename_plan find ALL callers, not 11-17%: canonicalize module uids (one node per physical file) and normalize import aliases (tools.X / thinking_os.tools.X / core.thinking_os.tools.X → one uid) so bare-name cross-module calls (ok()/fail() 11/63) and importers (0/6) resolve. Pairs with TASK-041 (instance-method receiver inference). Evidence: audit-graph-live-round5-2026-05-29.md.

## Read First
- docs/tasks/audits/audit-graph-live-round5-2026-05-29.md
- src/core/graph_os/extractors/code_python.py

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
- 2026-05-29 [claude]: ROOT-CAUSE PINNED (round-2 investigation, no code change). Recall gap is NOT reindex-fixable: full --force reindex left
- 2026-05-29 [claude]: PARTIAL FIX LANDED (commit 63b25bc): cross-file linking TIMING + PRECISION solved. graph-reindex now runs global link_ex
- 2026-05-29 [claude]: CALL-EMISSION RULED OUT — extractor is CORRECT. Direct code_python.extract(board_os/mcp_tools.py) emits 21 calls edges t
- 2026-05-29 [claude]: ABORT BUG FIXED (commit 7d43357): link_external_stubs now UPDATE OR IGNORE — a bare UPDATE aborted the whole pass on UNI
