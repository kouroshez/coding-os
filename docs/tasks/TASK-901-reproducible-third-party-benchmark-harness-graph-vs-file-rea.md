---
id: TASK-901
title: "Reproducible third-party benchmark harness: graph-vs-file-read on 2-3 public repos"
swimlane: core
kind: feature
epic: null
labels: [benchmark, credibility, ready]
status: icebox
priority: P2
appetite: 3d
created: 2026-08-08
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-901: Reproducible third-party benchmark harness: graph-vs-file-read on 2-3 public repos

**Outcome (one sentence):** An executable harness anyone can run on Django/FastAPI/requests reproducing the token-saving numbers with written methodology

## Read First
- docs/engineering/graph_os-queries.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a clean clone\n- **When** a stranger runs the harness entrypoint against a named public repo\n- **Then** it produces token_cost comparison (graph envelope vs grep+read) with methodology.md and raw numbers

## Work Log
