---
id: TASK-206
title: "Memory page: kill learned-pattern duplication + consumer-friendly UI"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-06
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-206: Memory page: kill learned-pattern duplication + consumer-friendly UI

**Outcome (one sentence):** learned_patterns dedups on a count-agnostic identity so re-extraction updates one row (re-confirmation tracked via times_validated) instead of inserting a new snapshot; existing duplicate rows collapse (16→4); the Hub Memory page renders a readable, high-contrast, consumer-useful table without the constant internal-weight noise columns.

## Read First
- [src/core/rules/memory.md](../../src/core/rules/memory.md) — memory layer policy + hygiene
- [src/core/thinking_os/tools/learning.py](../../src/core/thinking_os/tools/learning.py) — `learn_extract` / `_upsert_pattern` (the producer)
- [src/core/web/ui/src/pages/MemoryPage.tsx](../../src/core/web/ui/src/pages/MemoryPage.tsx) — the Hub view

## Repro Steps
1. Open the Hub Memory tab (/diagnostics/memory).
2. The table shows many near-identical rows: "INFRA domain succeeds at 100% (32/32 tasks) — reliable baseline", "(40/40)", "(83/83)" … and "Skill set '…' correlates with success (N tasks)" repeated.
Expected: one row per learned fact, readable, with useful signal.
Actual: 16 rows but only 4 distinct facts. Root cause: pattern TEXT embeds the running count `(N/N tasks)` and `_upsert_pattern` dedups on exact text — so each extraction run (count grew) inserts a NEW snapshot row instead of updating. The constant noise columns (Impact 0.50, Decay 0.10, tier 'volatile') add no consumer value.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** repeated `learn_extract` runs where a domain/skill's cumulative success count grows
- **When** the same underlying fact is re-mined
- **Then** `_upsert_pattern` matches it by a count-agnostic identity and UPDATES the single row (bumping times_validated as a re-confirmation signal) instead of inserting a duplicate; existing duplicates collapse (16→4); and the Memory page renders one readable, high-contrast row per fact without the constant internal-weight columns.

## Work Log
- 2026-06-06 [claude]: committed 07dff277: src/core/thinking_os/tests/test_learning.py, src/core/thinking_os/tools/learning.py, src/core/web/ui
- 2026-06-06 [claude]: learning.py: count-agnostic _pattern_identity + _collapse_duplicate_patterns; live DB 16→4; MemoryPage redesigned (cards
