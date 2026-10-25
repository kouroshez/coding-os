---
id: TASK-1078
title: "Hub Memory tab: read-only view of the file-based .agents/memory index, sub-indexes and lint health"
swimlane: core
kind: feature
epic: null
labels: [docs-update, hub, ready]
status: in_progress
priority: P2
appetite: 1d
created: 2026-10-25
started: 2026-10-24
completed: null
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1078: Hub Memory tab: read-only view of the file-based .agents/memory index, sub-indexes and lint health

**Outcome (one sentence):** The Hub Workspace again has a Memory tab, rebuilt for the file-based model: it shows MEMORY.md and each sub-index as grouped entries with type, verified date and body, plus the memory-lint verdict and the index load budget, without any database.

## Read First
- docs/engineering/hub-architecture.md
- src/core/rules/memory.md
- src/core/scripts/memory_lint.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a project with .agents/memory, **When** GET /api/memory is called, **Then** it returns the root index entries, each sub-index with its entries, every memory's frontmatter fields and body, the lint errors/warnings and the MEMORY.md line and byte budget.
- **Given** a project with no .agents/memory directory, **When** GET /api/memory is called, **Then** it returns present=false and the tab renders an empty state naming the folder, not an error.
- **Given** the Workspace tab bar, **When** the operator opens Memory, **Then** entries are grouped by index with counts, filterable by text and type, and a row expands to the memory body.

## Work Log
