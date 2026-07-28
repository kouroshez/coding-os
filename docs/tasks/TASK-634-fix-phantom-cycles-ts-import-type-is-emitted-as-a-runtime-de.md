---
id: TASK-634
title: "Fix phantom cycles: TS `import type` is emitted as a runtime dependency edge"
swimlane: "graph_os"
kind: bug
epic: cognitive-kernel-hardening
labels: [graph, typescript, false-positive, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-28
started: 2026-06-28
completed: 2026-06-28
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-634: Fix phantom cycles: TS `import type` is emitted as a runtime dependency edge

**Outcome (one sentence):** TypeScript type-only imports no longer pollute cos_graph_cycles / cos_graph_impact: the TS extractor tags type-only edges (reduced confidence + type_only metadata) and the cycle query excludes them, removing false-positive runtime cycles in the knowledge graph.

## Read First
- src/core/graph_os/extractors/code_ts.py
- src/core/graph_os/tools/graph.py
- tests/test_code_ts.py
- docs/engineering/graph-hallucination-cures.md

## Repro Steps
Given a .ts file with `import type { Foo } from './x'` participating in a type-only loop, When cos_graph_cycles runs, Then today it reports a phantom runtime cycle because the import regex matches `import type` but tags the edge identically to a value import (edge_type='imports', confidence=0.9, no type_only flag).

## Implementation Notes (verified against source 2026-06-28)
Import edges are emitted in exactly ONE place — `_extract_imports` (code_ts.py ~1027-1148), called once at ~line 879 for BOTH the tree-sitter and regex paths; `_walk_ts_symbols` does NOT emit import edges, so no walker change is needed (single emit site, not two). The fix: (1) add a named capture for the optional `type ` in `_IMPORT_RE` (~line 67), (2) thread a `type_only` flag to the `imports` edge emit (~1088-1098) — reduced confidence + type_only metadata so the cycle query can exclude it, (3) make cos_graph_cycles scope='imports' (graph.py ~4085-4091) exclude type-only edges, (4) flip `tests/test_code_ts.py::test_type_only_import` (~70-73), which today asserts a type-only import yields a runtime `imports` edge.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `import type {...}` or inline `{ type Foo }`, **When** extracted, **Then** the edge carries type_only=True metadata and reduced confidence.
- **Given** a loop formed only by type-only imports, **When** cos_graph_cycles runs, **Then** no cycle is reported.
- **Given** ordinary value imports, **When** extracted, **Then** behavior is unchanged (still edge_type='imports', full confidence).
- **Given** the graph_os matrix suite + the updated test_code_ts.py, **When** run, **Then** green; the change touches the single import emit site, the regex, the cycle query, and the existing type-only test.

## Work Log
- 2026-06-28 [claude]: Edit code_ts.py
- 2026-06-28 [claude]: Edit code_ts.py
- 2026-06-28 [claude]: Edit test_code_ts.py
- 2026-06-28 [claude]: Edit test_centrality_ranking_doctor.py
- 2026-06-28 [claude]: Edit graph.py
- 2026-06-28 [claude]: Edit commit634.txt
- 2026-06-28 [claude]: Fixed in code_ts.py: _IMPORT_RE now captures the optional `type ` (named group type_only); _extract_imports…
- 2026-06-28 [claude]: Status transitioned to complete via cos task-done.
