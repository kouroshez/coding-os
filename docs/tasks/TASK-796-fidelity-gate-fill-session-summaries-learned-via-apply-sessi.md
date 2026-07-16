---
id: TASK-796
title: "Fidelity gate + fill session_summaries.learned via apply_session_facts leaf"
swimlane: "thinking_os"
kind: feature
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-07-05
started: 2026-07-05
completed: 2026-07-05
agent_session: ses-claude-20260704-210156-0ee9
depends_on: []
blocked_by: []
references: []
---
# TASK-796: Fidelity gate + fill session_summaries.learned via apply_session_facts leaf

**Outcome (one sentence):** session_summaries.learned/investigated/next_steps are filled only when a session carries real signal (LLM has_signal + non-empty learned), via a deterministic apply_session_facts leaf; the misleading concept-graph 'Co-edited a<->b' husk is removed so an honest NULL replaces a fake lesson.

## Read First
- src/core/thinking_os/session_enrich.py
- src/core/thinking_os/cognition_schemas.py
- src/core/thinking_os/tests/test_session.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the Stop-time session_enrich currently derives session_summaries.learned from concept_graph co_edit edges (empty on 179/180 rows) **When** apply_session_facts(conn, session_id, SessionSummaryFacts) is called with has_signal True and non-empty learned **Then** learned/investigated/next_steps are COALESCE-written (first-write-wins, UPDATE-only), a no-signal or empty-learned facts object writes nothing (learned stays NULL), and the 'Co-edited' husk is gone (grep returns nothing).

## Work Log
- 2026-07-05 [claude]: Edit session_enrich.py
- 2026-07-05 [claude]: Edit session_enrich.py
- 2026-07-05 [claude]: Edit cognition_schemas.py
- 2026-07-05 [claude]: Edit test_session.py
- 2026-07-05 [claude]: cognition_schemas.py: +SessionSummaryFacts model. session_enrich.py: +_has_session_signal + apply_session_facts…
- 2026-07-05 [claude]: committed a759a73d · 3 files
