---
id: TASK-633
title: "Add MMR diversity, multi-field FTS5 weighting, and RRF fusion to cos_search ranking"
swimlane: core
kind: feature
epic: cognitive-kernel-hardening
labels: [memory, retrieval, ranking, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-28
started: 2026-06-28
completed: 2026-06-28
agent_session: ses-claude-20260625-235014-c028
depends_on: []
blocked_by: []
references: []
---
# TASK-633: Add MMR diversity, multi-field FTS5 weighting, and RRF fusion to cos_search ranking

**Outcome (one sentence):** cos_search returns more diverse, higher-precision memory results: near-duplicate crowding is cut via MMR re-ranking, title/pattern hits outrank body hits via column-weighted FTS5 bm25, and lexical+semantic candidate lists fuse via Reciprocal Rank Fusion — all inside memory.py with zero new dependencies (reuse numpy + existing FTS5).

## Read First
- src/core/thinking_os/tools/memory.py
- src/core/thinking_os/database.py
- src/core/rules/memory.md
- src/core/skills/search/SKILL.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** two near-duplicate memories, **When** cos_search ranks, **Then** MMR (lambda~0.7, token-Jaccard on title+concepts) keeps only the top one in the diverse slice.
- **Given** a query term in a pattern title vs the same term in body, **When** ranked, **Then** the title hit scores higher via FTS5 bm25 column weights (title>narrative~concepts).
- **Given** both an FTS5 lexical list and a semantic list, **When** merged, **Then** RRF (k=60, keyed on (source_table,id)) yields the fused order with dedup, not duplication.
- **Given** the thinking_os matrix suite, **When** run, **Then** it stays green (no ranking regression on the dogfood corpus).

## Work Log
- 2026-06-28 [claude]: Edit bm25_check.py
- 2026-06-28 [claude]: Edit bm25_check.py
- 2026-06-28 [claude]: Edit memory.py
- 2026-06-28 [claude]: Edit memory.py
- 2026-06-28 [claude]: Edit memory.py
- 2026-06-28 [claude]: Edit memory.py
- 2026-06-28 [claude]: Edit memory.py
- 2026-06-28 [claude]: Edit memory.py
- 2026-06-28 [claude]: Edit memory.py
- 2026-06-28 [claude]: Edit memory.py
- 2026-06-28 [claude]: Edit memory.py
- 2026-06-28 [claude]: Edit memory.py
- 2026-06-28 [claude]: Edit test_memory.py
- 2026-06-28 [claude]: Edit test_memory.py
- 2026-06-28 [claude]: Edit test_memory.py
- 2026-06-28 [claude]: Edit commit633.txt
- 2026-06-28 [claude]: Implemented in memory.py: column-weighted bm25(title=3) + corrected inverted relevance mapping (empirically verified…
- 2026-06-28 [claude]: Status transitioned to complete via cos task-done.
