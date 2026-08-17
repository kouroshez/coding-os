---
id: TASK-1011
title: "Finish the README screenshot set and stop the search summary counting unanswered layers as zero"
swimlane: core
kind: bug
epic: null
labels: [ui, design, search, readme, docs-update, ready]
status: in_progress
priority: P2
appetite: 4h
created: 2026-08-17
started: 2026-08-17
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-1011: Finish the README screenshot set and stop the search summary counting unanswered layers as zero

**Outcome (one sentence):** The five tabs the operator asked for are all in the README, and the unified search summary never prints a count for a layer that has not answered yet.

## Read First
- src/core/web/ui/src/features/search/UnifiedSearch.tsx
- README.md
- src/core/web/ui/src/features/search/SearchPrimitives.tsx

## Repro Steps
Open http://127.0.0.1:9188/p/coding-os/workspace/search, type "wip limit", press Search. The summary line renders `16 results for "wip limit" · Memory 0 · Docs 0 · Tasks 0 · Graph 16` while the MEMORY, DOCS and TASKS sections directly beneath it still render `loading…`. `totals.memory = memory.data?.results?.length ?? 0` collapses "in flight" to zero.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a submitted query whose memory layer is still in flight **When** the summary chip for Memory renders **Then** it shows a pending marker rather than the number 0. **When** any layer is still in flight **Then** the total is marked provisional rather than presented as final. **Given** every layer has answered **Then** the summary renders exactly as it does today.

## Work Log
- 2026-08-17 [claude]: Edit UnifiedSearch.tsx
- 2026-08-17 [claude]: Edit UnifiedSearch.tsx
- 2026-08-17 [claude]: Edit UnifiedSearch.tsx
- 2026-08-17 [claude]: Edit LogsPage.tsx
- 2026-08-17 [claude]: Edit shoot.mjs
- 2026-08-17 [claude]: Edit jobs4.json
