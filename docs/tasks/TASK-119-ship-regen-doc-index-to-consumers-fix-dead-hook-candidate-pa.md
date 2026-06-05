---
id: TASK-119
title: "Ship regen_doc_index to consumers + fix dead hook candidate path — 00-index regen is a no-op in every cos init"
swimlane: core
kind: bug
epic: doc-system
labels: [docs-system, dogfood, graph, audit-d7-f3, overlap-TASK-113, ready]
status: icebox
priority: P1
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-119: Ship regen_doc_index to consumers + fix dead hook candidate path — 00-index regen is a no-op in every cos init

**Outcome (one sentence):** auto-regen-doc-index.sh resolves its generator inside a consumer project (preferably by calling a shipped CLI surface e.g. cos docs-index --regen-nav <dir> rather than scaffolding a loose script), so docs/<dir>/00-index.md freshness works in every organism, not just the meta-repo dogfood path. Also fixes the relative-path exit-127 invocation breakage and the omitted Nav line.

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- src/core/hooks/auto-regen-doc-index.sh
- src/scripts/regen_doc_index.py
- src/core/scaffold_manifest.json

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
