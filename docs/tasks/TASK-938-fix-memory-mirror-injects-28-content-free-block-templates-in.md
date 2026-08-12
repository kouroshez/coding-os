---
id: TASK-938
title: "fix: memory mirror injects 28 content-free block templates into every session"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-12
started: 2026-08-11
completed: 2026-08-11
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-938: fix: memory mirror injects 28 content-free block templates into every session

**Outcome (one sentence):** The MEMORY.md generated block carries only information-bearing lessons — zero placeholder rows whose text ends in a generic friction hint — and the mirror never re-imports its own output as a belief.

## Read First
- src/adapters/claude/hooks/agent_memory_sync.py
- src/core/thinking_os/tools/_learning_mining.py
- src/core/rules/memory.md

## Repro Steps
Measured on the live DB 2026-08-11 (`.coding-os/coding-os.db`):
- The mirror predicate `confidence>=0.7 AND times_seen>=3 AND memory_type!='stat' AND promoted_to IS NULL` selects **30** rows, of which **28 (93%)** end in the generic hint `→ satisfy the blocked rule before retrying the action`. `render_mirror` writes those 30 verbatim into `.agents/memory/MEMORY.md`, which the runtime loads into **every** session's context.
- Root cause: `_mint_friction_lesson` writes a deterministic **placeholder** when distillation is unavailable, and gives it `confidence = min(0.85, 0.4 + count/10)` — so recurrence alone lifts a placeholder above 0.7. Real distilled lessons are minted at a flat 0.5 and are therefore **suppressed**: 40 `llm_distilled` rows exist and none reach the mirror.
- 49 of 113 patterns (43%) end in one of the three `_FRICTION_HINTS` strings.
- Separately `harvest()` re-reads MEMORY.md itself and minted `learned_patterns` id=226 pattern='Memory Index' (times_seen=4, still reinforcing) and id=227 pattern='---'.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the live DB **When** `_trusted_lessons` runs **Then** zero returned rows end in a generic friction hint, and distilled lessons appear.
**Given** MEMORY.md holding the generated block plus a human index **When** `harvest` runs **Then** it mints zero patterns out of MEMORY.md itself.
**Given** the existing junk rows id=226 and id=227 **When** the cleanup runs **Then** they are absent from `learned_patterns`.

## Work Log
- 2026-08-12 [claude]: Edit _learning_mining.py
- 2026-08-12 [claude]: Edit agent_memory_sync.py
- 2026-08-12 [claude]: Edit agent_memory_sync.py
- 2026-08-12 [claude]: Edit agent_memory_sync.py
- 2026-08-12 [claude]: Edit test_agent_memory_sync.py
- 2026-08-12 [claude]: Edit clean_memory.py
- 2026-08-12 [claude]: commit ba79946c2d — fix(memory): render distilled lessons in the agent-memory mirror, not block counters
- 2026-08-12 [claude]: Live DB: mirror 30 rows/28 placeholders -> 25 rows/0 placeholders; junk ids 226,227 deleted; Stop hook run, 0 harvested.
- 2026-08-12 [claude]: Status transitioned to complete via cos task-done.
