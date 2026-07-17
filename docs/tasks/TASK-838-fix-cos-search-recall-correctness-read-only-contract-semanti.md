---
id: TASK-838
title: "fix cos_search recall correctness: read-only contract, semantic filter bypass, FTS5 escaping"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-07-17
started: 2026-07-17
completed: 2026-07-17
agent_session: ses-claude-20260717-014556-89d0
depends_on: []
blocked_by: []
references: []
---
# TASK-838: fix cos_search recall correctness: read-only contract, semantic filter bypass, FTS5 escaping

**Outcome (one sentence):** cos_search stops inflating learned_pattern confidence on every read (honoring its TASK-109 read-only contract), applies min_confidence/since_days to the semantic channel too, and escapes the FTS5 MATCH query so natural-language queries stop silently falling back to whole-phrase LIKE — closing the recall-correctness cluster of the memory audit.

## Read First
- src/core/thinking_os/tools/memory.py
- src/core/rules/memory.md
- src/core/rules/api-contract-discipline.md

## Repro Steps
Call cos_search twice for a query matching a learned_pattern; observe confidence rises +0.02 each call (memory.py:560-564, _boost_access 104-113). Call cos_search with a multi-word query containing a colon; observe FTS OperationalError swallowed → whole-phrase LIKE → 0 hits (memory.py:390-403).

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a learned_pattern at confidence 0.60 **When** cos_search returns it **Then** its confidence is unchanged (no +0.02 write-on-read); **And Given** a low-confidence/old semantic-only hit **When** min_confidence=0.3 or since_days is set **Then** it is filtered out of the semantic channel too; **And Given** a natural-language query containing FTS5 metacharacters (colon, quotes, AND/OR) **When** cos_search runs **Then** it returns keyword matches instead of erroring into a whole-phrase LIKE 0-hit.

## Work Log
- 2026-07-17 [claude]: Edit memory.py
- 2026-07-17 [claude]: Edit memory.py
- 2026-07-17 [claude]: Edit memory.py
- 2026-07-17 [claude]: Edit memory.py
- 2026-07-17 [claude]: Edit memory.py
- 2026-07-17 [claude]: Edit memory.py
- 2026-07-17 [claude]: Edit memory.py
- 2026-07-17 [claude]: Edit memory.py
- 2026-07-17 [claude]: Fixed 3 recall-correctness bugs in memory.py: (a) removed the write-on-read confidence/access boost from…
- 2026-07-17 [claude]: committed 435bc5a7 · 2 files
