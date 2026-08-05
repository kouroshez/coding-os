---
id: TASK-801
title: "Split conflated learned_patterns counter: times_seen (occurrence) vs times_validated (real validation) \u2014 v49"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-07-05
started: 2026-07-05
completed: 2026-07-05
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-801: Split conflated learned_patterns counter: times_seen (occurrence) vs times_validated (real validation) — v49

**Outcome (one sentence):** `learned_patterns.times_validated` stops being a fraud counter — occurrence re-mines and dedup folds move to a new `times_seen`, leaving `times_validated` to reflect only real validation events, so trust ranking and the MEMORY.md badge read an honest signal.

## Read First
- src/core/thinking_os/tools/learning.py (`_upsert_pattern`:698, `_collapse_duplicate_patterns`:460/468, `_consolidate_semantic_duplicates`:503/520, distilled-merge fold:908)
- src/adapters/claude/hooks/agent_memory_sync.py (`_trusted_lessons` — the "seen N×" badge)
- src/core/thinking_os/database.py (MIGRATIONS list; append v49)

## Repro Steps
1. Inspect the live DB: `MAX(times_validated)` is ~533 despite `pattern_validations` being empty.
2. `_upsert_pattern` bumps `times_validated + 1` on every RE-MINE (recurrence), and the two dedup paths fold losers' `times_validated` into the survivor — so the counter measures OCCURRENCES, not validations.
Expected: `times_validated` counts real validation events only; occurrences live in their own column.
Actual: the two are conflated in one column, inflating trust tiers and the badge off pure recurrence.

## Scope (this task = the counter split; validation-firing wiring is TASK-802)
- v49: `ADD COLUMN times_seen INTEGER DEFAULT 0`, backfill `times_seen = COALESCE(times_validated, 0)` (historically times_validated WAS the occurrence count).
- Repoint the OCCURRENCE bumps (re-mine + both dedup folds + distilled-merge fold) from `times_validated` to `times_seen`; leave the REAL-validation bumps (`_boost_success`, `_log_validation`) on `times_validated` untouched.
- `_trusted_lessons`: gate + display on `times_seen` (coordinates with the L badge relabel).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a learned pattern re-mined N times with zero real validations,
- **When** the split is applied,
- **Then** `times_seen == N` and `times_validated == 0`; a dedup merge sums `times_seen` (not `times_validated`) into the survivor; the badge reads `times_seen`; the v49 backfill sets `times_seen = old times_validated`; and the thinking_os matrix + `server.py --test` stay green.

## Work Log
- 2026-07-05 [claude]: Edit database.py
- 2026-07-05 [claude]: Edit database.py
- 2026-07-05 [claude]: Edit learning.py
- 2026-07-05 [claude]: Edit learning.py
- 2026-07-05 [claude]: Edit learning.py
- 2026-07-05 [claude]: Edit learning.py
- 2026-07-05 [claude]: Edit learning.py
- 2026-07-05 [claude]: Edit learning.py
- 2026-07-05 [claude]: Edit learning.py
- 2026-07-05 [claude]: Edit learning.py
- 2026-07-05 [claude]: Edit agent_memory_sync.py
- 2026-07-05 [claude]: Edit agent_memory_sync.py
- 2026-07-05 [claude]: Edit test_db.py
- 2026-07-05 [claude]: Edit test_agent_memory_sync.py
- 2026-07-05 [claude]: Edit test_distill.py
- 2026-07-05 [claude]: Edit test_learning.py
- 2026-07-05 [claude]: Counter split implemented: v49 adds times_seen (backfilled from times_validated, NO reset); the occurrence-write…
- 2026-07-05 [claude]: commit eae440c4b8 — fix(memory): split conflated times_validated into times_seen vs times_validated (v49)
- 2026-07-05 [claude]: Status transitioned to complete via cos task-done.
