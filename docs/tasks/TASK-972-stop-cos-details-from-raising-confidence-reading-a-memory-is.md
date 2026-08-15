---
id: TASK-972
title: "Stop cos_details from raising confidence: reading a memory is not evidence"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [memory, contract-drift, P1, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-14
started: 2026-08-14
completed: 2026-08-14
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-972: Stop cos_details from raising confidence: reading a memory is not evidence

**Outcome (one sentence):** A learned pattern's confidence moves only on validation evidence, so retrieval popularity can no longer inflate a belief the system has not re-confirmed.

## Read First
- src/core/rules/memory.md § Memory hygiene rules
- src/core/thinking_os/tools/_memory_ranking.py:86-106
- src/core/thinking_os/tools/memory.py:184

## Repro Steps
memory.md states confidence moves by LTP/LTD only via cos_learn_validate and that "there is no tool that writes a confidence number". But _boost_access, called from memory_details (cos_details), runs `confidence = MIN(0.95, confidence + 0.02)` on learned_patterns. Fifty detail views drive any pattern to the 0.95 ceiling with zero confirming evidence.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a learned pattern at confidence C, **When** cos_details is called on it N times, **Then** its confidence is still C and only access_count/last_accessed_at changed.
- **Given** the same pattern, **When** cos_learn_validate confirms it, **Then** confidence rises as before.
- **Given** ranking, **When** a frequently-read pattern is scored, **Then** access still contributes through the access-recency signal, not through the confidence term.

## Work Log
- 2026-08-14 [claude]: Edit _memory_ranking.py
- 2026-08-14 [claude]: Edit _tools_recall.py
- 2026-08-14 [claude]: Edit _memory_search.py
- 2026-08-14 [claude]: Edit msg6.txt
- 2026-08-14 [claude]: commit e502c12ca9 — fix(memory): reading a pattern no longer raises its confidence
- 2026-08-14 [claude]: Fixed in e502c12c: _boost_access now touches access_count/last_accessed_at only. Also retired two stale comments that…
- 2026-08-14 [claude]: Status transitioned to complete via cos task-done.
