---
id: TASK-039
title: "Deep audit + benchmark: graph_os subsystem & cos_graph_* MCP tools"
swimlane: infra
kind: chore
epic: null
labels: []
status: complete
priority: P2
appetite: "1d"
created: 2026-05-28
started: 2026-05-28
completed: 2026-05-29
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-039: Deep audit + benchmark: graph_os subsystem & cos_graph_* MCP tools

**Outcome (one sentence):** Exhaustively validate graph_os node/edge accuracy and every `cos_graph_*` MCP tool against the live repo, recording all findings + root causes + fix sites in the audit artifact.

## Read First
- docs/tasks/audits/audit-graph-system-deep-2026-05-28.md — the audit artifact (findings register + coverage table)
- src/core/graph_os/backends/sqlite_backend.py — upsert_node merge logic (lines 185-272)
- src/core/graph_os/extractors/md_links.py — _promote_stubs / _stub_for_uid
- src/core/graph_os/ingest/base.py — walk filter SSOT

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the graph_os subsystem + all 17 `cos_graph_*` tools
- **When** each audit category (D1–D8) is exercised and cross-verified against the repo
- **Then** every finding has evidence + severity + fix site recorded in the audit doc, and the EvidenceBundle is submitted

## Work Log
- 2026-05-28 [claude]: audit started — D1–D3 + root cause complete; see audit doc.
- 2026-05-29 [claude]: Live re-verification: file coverage 100% (1072/1072), F1/F2 confirmed fixed, impact sound, F5 = stale server (disk corre
- 2026-05-29 [claude]: Status transitioned to complete via cos task-done.
