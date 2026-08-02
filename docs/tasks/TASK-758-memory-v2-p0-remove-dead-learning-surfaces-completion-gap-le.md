---
id: TASK-758
title: "memory-v2 P0: remove dead learning surfaces (completion_gap, learn_feedback) + honest pulse metrics"
swimlane: core
kind: refactor
epic: memory-v2
labels: [memory, governance, docs-update, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-07-02
started: 2026-07-02
completed: 2026-07-02
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-758: memory-v2 P0: remove dead learning surfaces (completion_gap, learn_feedback) + honest pulse metrics

**Outcome (one sentence):** Learning pipeline has zero dead read-paths, cos_learn_feedback is removed from the MCP surface, and the pulse [Memory] line reports only measured values.

## Read First
- docs/engineering/learning-extraction.md
- docs/governance/mcp-tool-inventory.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the cleaned repo, **When** grepping completion_gap under src/, **Then** only append-only migration history remains
- **Given** the MCP server, **When** listing tools, **Then** cos_learn_feedback is absent and mcp-tool-inventory.md reflects it
- **Given** a session start, **When** the [Memory] pulse line renders, **Then** it contains only measured values (no hardcoded 700, no cumulative capture-cost)

## Work Log
- 2026-07-02 [claude]: Edit learning-extraction.md
- 2026-07-02 [claude]: Edit learning-extraction.md
- 2026-07-02 [claude]: Edit learning-extraction.md
- 2026-07-02 [claude]: Edit learning-extraction.md
- 2026-07-02 [claude]: Edit learning-extraction.md
- 2026-07-02 [claude]: Edit learning.py
- 2026-07-02 [claude]: Edit learning.py
- 2026-07-02 [claude]: Edit learning.py
- 2026-07-02 [claude]: Edit learning.py
- 2026-07-02 [claude]: Edit session_enrich.py
- 2026-07-02 [claude]: Edit learning.py
- 2026-07-02 [claude]: Edit learning.py
- 2026-07-02 [claude]: Edit session_startup.py
- 2026-07-02 [claude]: Edit session_enrich.py
- 2026-07-02 [claude]: P0 complete (commit 5192ef97): removed completion_gap dead read-paths, retired cos_learn_feedback across…
- 2026-07-02 [claude]: Status transitioned to complete via cos task-done.
