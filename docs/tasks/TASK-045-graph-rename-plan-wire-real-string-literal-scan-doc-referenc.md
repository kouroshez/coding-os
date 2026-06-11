---
id: TASK-045
title: "graph rename_plan: wire real string-literal scan + doc_references (check_strings silent no-op)"
swimlane: infra
kind: bug
epic: null
labels: []
status: complete
priority: P1
appetite: "1d"
created: 2026-05-29
started: null
completed: 2026-05-29
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-045: graph rename_plan: wire real string-literal scan + doc_references (check_strings silent no-op)

**Outcome (one sentence):** cos_graph_rename_plan.string_literals returns real ripgrep hits (currently a permanent [] stub via the MCP path — check_strings=true silently misses runtime-breaking string refs) and doc_references reflects actual doc mentions (currently 0 with result_truncated=false = false 'docs covered').

## Read First
- src/core/graph_os/tools/graph.py

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
- 2026-05-29 [claude]: DONE — wired real ripgrep string-literal scan (was [] stub); verified live (finds 'SqliteBackend' registry string keys A
