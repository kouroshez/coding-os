---
id: TASK-793
title: "Relabel MEMORY.md trusted-lessons badge: validated \u2192 seen"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-07-05
started: 2026-07-04
completed: 2026-07-04
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-793: Relabel MEMORY.md trusted-lessons badge: validated → seen

**Outcome (one sentence):** MEMORY.md Trusted-lessons badge stops presenting re-derivation counts (times_validated, bumped on every re-mine) as helpfulness; shows honest 'seen N×', converging with the Hub which already renders 'Seen N×'.

## Read First
- src/adapters/claude/hooks/agent_memory_sync.py
- src/core/web/ui/src/pages/MemoryPage.tsx
- tests/test_agent_memory_sync.py

## Repro Steps
Inspect .agents/memory/MEMORY.md Trusted-lessons block: badge reads '_(validated N×)_' where N = learned_patterns.times_validated, which learning.py:_upsert_pattern increments on every re-mine (not on real validation) — MAX(times_validated)=533 while pattern_validations=0.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a trusted pattern (confidence>=0.7, times_validated>=3)
**When** render_mirror generates the MEMORY.md block for MEMORY.md
**Then** the rendered line emits '_(seen N×)_' and never '_(validated', and tests/test_agent_memory_sync.py stays green with the two new assertions.

## Work Log
- 2026-07-05 [claude]: Edit agent_memory_sync.py
- 2026-07-05 [claude]: Edit test_agent_memory_sync.py
- 2026-07-05 [claude]: Changed agent_memory_sync.py:43 badge 'validated'→'seen' (number unchanged); +2 assertions in…
- 2026-07-05 [claude]: committed 8a85d69c · 2 files
