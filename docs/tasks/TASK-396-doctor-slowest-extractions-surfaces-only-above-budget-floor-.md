---
id: TASK-396
title: "Doctor: slowest_extractions surfaces only above budget floor + hub serves stale doctor code"
swimlane: "graph_os"
kind: bug
epic: null
labels: [graph-os, doctor, hub, ready]
status: archive
priority: P2
appetite: 2h
created: 2026-06-11
started: 2026-06-11
completed: 2026-06-11
agent_session: ses-claude-20260611-120804-a06f
depends_on: []
blocked_by: []
references: []
---
# TASK-396: Doctor: slowest_extractions surfaces only above budget floor + hub serves stale doctor code

**Outcome (one sentence):** Hub Doctor Backend tab shows ISSUES=0 after a clean build: slowest_extractions appears in issues[] only when the top duration exceeds the 500ms budget floor (always available as stats.slowest_extraction_ms), duration telemetry is refreshed by a clean sequential run instead of the lock-contended parallel run, and the long-lived hub process is restarted so it serves the new issue_count semantics instead of stale code.

## Read First
- src/core/graph_os/tools/graph.py
- docs/playbooks/polyglot-extractor-roadmap.md
- docs/engineering/mcp-error-envelope.md

## Repro Steps
1. After TASK-395 shipped issue_count=real-only, open Hub → Diagnostics → Doctor → Backend (hub process up for 15h, started before the change).
2. Badge shows ISSUES=1 although CLI doctor reports issue_count=0 — the hub serves the pre-change module (meta.server_stale).
3. The slowest_extractions card always lists top-10 durations even when every row is inside the roadmap §7 budget; after the contended -j4 force run the recorded durations are inflated (1029ms top), reading as a problem when it is contention telemetry.
Expected: badge 0, no slowest card when within budget. Actual: badge 1 + permanent 10-row card.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** file_index_state rows whose max duration_ms is below 500, **When** cos_graph_doctor runs, **Then** issues[] has no slowest_extractions entry and stats.slowest_extraction_ms still reports the max.
- **Given** a row above 500ms, **When** doctor runs, **Then** the slowest_extractions info entry appears with its budget_floor_ms.
- **Given** a fresh sequential force reindex and a restarted hub, **When** the Doctor Backend tab loads, **Then** HEALTH=ok and ISSUES=0.

## Work Log
- 2026-06-11 [claude]: Edit polyglot-extractor-roadmap.md
- 2026-06-11 [claude]: Edit graph.py
- 2026-06-11 [claude]: Edit graph.py
- 2026-06-11 [claude]: Edit test_centrality_ranking_doctor.py
- 2026-06-11 [claude]: slowest_extractions now surfaces in issues[] only above the 500ms roadmap floor (stats.slowest_extraction_ms always pres
- 2026-06-11 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-11 [claude]: committed a458d5db: docs/playbooks/polyglot-extractor-roadmap.md, src/core/graph_os/tests/test_centrality_ranking_doctor
