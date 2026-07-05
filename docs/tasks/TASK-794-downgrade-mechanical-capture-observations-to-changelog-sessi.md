---
id: TASK-794
title: "Downgrade mechanical capture observations to changelog + session-wide write-dedup"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [ready]
status: testing
priority: P2
appetite: 1d
created: 2026-07-05
started: 2026-07-04
completed: null
agent_session: ses-claude-20260704-210156-0ee9
depends_on: []
blocked_by: []
references: []
---
# TASK-794: Downgrade mechanical capture observations to changelog + session-wide write-dedup

**Outcome (one sentence):** Mechanical auto-capture rows ('Modified/Created path') become a hidden 'changelog' memory_type excluded from recall/digest, deduped once per (tool,file,session), so cos_search stops being flooded by 96% edit-recap noise the memory.md policy already forbids.

## Read First
- src/core/thinking_os/capture.py
- src/core/thinking_os/tools/memory.py
- src/core/thinking_os/database.py
- src/core/rules/memory.md

## Repro Steps
capture.py:_build_narrative is rule-based 'free, instant, no API'; live DB has 4561/4737 (96.3%) 'Modified/Created path' mechanical rows flooding recall despite memory.md:22 forbidding 'I just did X' recaps; 30s content_hash dedup window leaves ~2.5x duplication; read-time title band-aid at memory.py:496 compensates downstream.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the PostToolUse capture path writes one observation per Write/Edit/MultiEdit **When** a file is edited N times in one session and memory_search/timeline run **Then** exactly one 'changelog'-typed row exists per (tool,file,session), changelog rows are excluded from memory_search and memory_timeline unless memory_type='changelog' is explicitly passed, and the v48 data-backfill reclassifies legacy write/edit/multiedit rows to changelog while leaving tool_failure rows untouched.

## Work Log
- 2026-07-05 [claude]: Edit capture.py
- 2026-07-05 [claude]: Edit capture.py
- 2026-07-05 [claude]: Edit capture.py
- 2026-07-05 [claude]: Edit memory.py
- 2026-07-05 [claude]: Edit memory.py
- 2026-07-05 [claude]: Edit memory.py
- 2026-07-05 [claude]: Edit memory.py
- 2026-07-05 [claude]: Edit memory.py
- 2026-07-05 [claude]: Edit memory.py
- 2026-07-05 [claude]: Edit memory.py
- 2026-07-05 [claude]: Edit database.py
- 2026-07-05 [claude]: Edit database.py
- 2026-07-05 [claude]: Edit test_capture.py
- 2026-07-05 [claude]: Edit test_capture.py
- 2026-07-05 [claude]: Edit test_capture.py
- 2026-07-05 [claude]: Edit test_capture.py
- 2026-07-05 [claude]: Edit test_capture.py
- 2026-07-05 [claude]: Edit memory.py
- 2026-07-05 [claude]: capture.py: memory_type='changelog' unconditional + session-wide content_hash dedup + removed dead…
