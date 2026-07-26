---
id: TASK-580
title: "Fix stale context-budget banner marker after /compact (reads pre-compact usage)"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-25
started: 2026-06-25
completed: 2026-06-25
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-580: Fix stale context-budget banner marker after /compact (reads pre-compact usage)

**Outcome (one sentence):** The ctx=Nk>200k banner marker reflects the live post-compaction context, not the stale pre-compact usage record. Immediately after /compact it is suppressed until a real post-compact usage record exists.

## Read First
- src/core/rules/transparency-banner.md
- src/core/hooks/_helpers/context_budget.py
- src/core/hooks/session-context.sh

## Repro Steps
Run /compact in a large session (e.g. 516k ctx). On the very next prompt the banner shows ctx=516k>200k even though /compact reported ~520k freed. Root cause: last_context_tokens() scans backward past the compact boundary to the last pre-compact assistant usage record (transcript line still present, no post-compact usage record exists yet at UserPromptSubmit time).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a transcript whose most recent `usage` record precedes a `compact_boundary` / `isCompactSummary` record **When** context_budget.py scans backward **Then** it returns 0 (marker suppressed), not the pre-compact total.
- **Given** a normal transcript with a `usage` record after the last compact boundary **When** it scans backward **Then** it returns that record's token sum exactly as before.
- **Given** the fix lands **When** `make verify-hooks` and the new helper test run **Then** both pass.

## Work Log
- 2026-06-25 [claude]: Edit context_budget.py
- 2026-06-25 [claude]: Edit context_budget.py
- 2026-06-26 [claude]: Edit test_context_budget.py
- 2026-06-26 [claude]: Root-caused: last_context_tokens() scanned backward past the compact boundary to the last pre-compact usage record…
- 2026-06-26 [claude]: committed 1022a4ab · 2 files
- 2026-06-26 [claude]: Status transitioned to complete via cos task-done.
