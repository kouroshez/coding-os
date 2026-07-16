---
id: TASK-771
title: "Fix Hub API contract-drift: Observability id, CommandPalette custom_title, search-memory body, trace size_bytes NaN"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-07-04
started: 2026-07-03
completed: 2026-07-04
agent_session: ses-claude-20260703-210450-473d
depends_on: []
blocked_by: []
references: []
---
# TASK-771: Fix Hub API contract-drift: Observability id, CommandPalette custom_title, search-memory body, trace size_bytes NaN

**Outcome (one sentence):** Four verified producer/consumer field-name mismatches are closed: ObservabilityPage reads the card id key the board actually emits; CommandPalette reads custom_title; memory search results carry an expandable content body; trace rows without a jsonl file render 0kb not NaNkb. Two audit items (config skills 'core', ContextPanel source_uid) confirmed non-issues and left untouched.

## Read First
- src/core/web/ui/src/pages/ObservabilityPage.tsx
- src/core/web/ui/src/features/palette/CommandPalette.tsx
- src/core/thinking_os/tools/memory.py
- src/core/web/routes/observability.py

## Repro Steps
Open Hub Observability tab → in-progress task id cells show '?'. Open CommandPalette → sessions with custom titles show the session id. Search memory in UnifiedSearch → expand a hit → body is empty. Cognition traces list → session-only rows show 'NaN.0kb'.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the board daily in_progress/blockers cards (which emit key `id`) **When** ObservabilityPage renders a row **Then** the mono id cell shows the real task id, not `?`. **Given** a chat session with a `custom_title` and no summary **When** CommandPalette lists it **Then** the label is the custom_title, not the raw session id. **Given** a memory search hit **When** the row is expanded in UnifiedSearch **Then** a content body renders. **Given** a session with no jsonl trace file **When** TraceList renders its size **Then** it shows 0.0kb, not NaN.0kb.

## Work Log
- 2026-07-04 [claude]: Edit ObservabilityPage.tsx
- 2026-07-04 [claude]: Edit ObservabilityPage.tsx
- 2026-07-04 [claude]: Edit CommandPalette.tsx
- 2026-07-04 [claude]: Edit CommandPalette.tsx
- 2026-07-04 [claude]: Edit observability.py
- 2026-07-04 [claude]: Edit memory.py
- 2026-07-04 [claude]: Edit memory.py
- 2026-07-04 [claude]: Edit memory.py
- 2026-07-04 [claude]: Edit memory.py
- 2026-07-04 [claude]: Edit memory.py
- 2026-07-04 [claude]: Edit search.py
- 2026-07-04 [claude]: Independently re-verified the audit: 2 of 6 flagged points are non-issues and left untouched (config skills 'core' is…
- 2026-07-04 [claude]: committed 3bae64f7 · 5 files
- 2026-07-04 [claude]: Status transitioned to complete via cos task-done.
