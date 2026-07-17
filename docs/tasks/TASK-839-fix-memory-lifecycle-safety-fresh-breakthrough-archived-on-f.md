---
id: TASK-839
title: "fix memory lifecycle safety: fresh breakthrough archived on first decay + trust_tier decay abort"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: testing
priority: P1
appetite: 1d
created: 2026-07-17
started: 2026-07-17
completed: null
agent_session: ses-claude-20260717-014556-89d0
depends_on: []
blocked_by: []
references: []
---
# TASK-839: fix memory lifecycle safety: fresh breakthrough archived on first decay + trust_tier decay abort

**Outcome (one sentence):** learn_narrative breakthrough patterns are born with a fresh last_validated so decay does not archive them on the first run (closing the reopened TASK-104 drift), and the decay loop excludes trust_tier locked/core so a promoted pattern can never make the protect trigger abort the entire decay run.

## Read First
- src/core/thinking_os/decay.py
- src/core/thinking_os/tools/learning.py
- docs/engineering/learning-extraction.md

## Repro Steps
learn_narrative INSERT (learning.py:1741) omits last_validated/last_accessed_at → NULL → decay months=999 → archived at floor on first run. decay SELECT (decay.py:233) has no trust_tier filter → a locked/core row hits trg_learned_patterns_protect_update → RAISE(ABORT) → whole decay run rolled back silently.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a learn_narrative breakthrough pattern (confidence 0.3, fresh) **When** run_decay executes **Then** it is NOT archived (last_validated stamped → age 0, not 999); **And Given** a learned_pattern with trust_tier='locked' **When** run_decay executes **Then** the run completes and commits (the protect trigger does not ABORT it) because locked/core rows are excluded from the decay UPDATE.

## Work Log
- 2026-07-17 [claude]: Edit learning.py
- 2026-07-17 [claude]: Edit decay.py
- 2026-07-17 [claude]: Edit decay.py
- 2026-07-17 [claude]: Edit decay.py
- 2026-07-17 [claude]: Fixed 2 lifecycle-safety bugs: (1) learn_narrative breakthrough INSERT now stamps…
- 2026-07-17 [claude]: committed 7fca22b7 · 4 files
