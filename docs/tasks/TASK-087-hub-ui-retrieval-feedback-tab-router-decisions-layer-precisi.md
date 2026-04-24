---
id: TASK-087
title: "Hub UI: Retrieval Feedback tab — router decisions, layer precision, thumbs-up/down flow"
swimlane: core
kind: feature
epic: hub-tab-scaffold
labels: [hub, ui, retrieval, feedback]
status: icebox
priority: P3
appetite: "5h"
created: 2026-04-24
started: null
completed: null
agent_session: null
depends_on: [TASK-072]
blocked_by: []
references: [TASK-017, TASK-018]
---

# TASK-087: Hub UI — Retrieval Feedback tab

**Outcome (one sentence):** Operators open `/retrieval` in the Hub, see every `cos_retrieve` call (query, hint, chosen layer, result count, click-through) and can mark good/bad outcomes; that feedback feeds back into the router score normalizer (TASK-017) so precision improves over time.

## Read First

- [core/thinking_os/tools/retrieve.py](../../core/thinking_os/tools/retrieve.py) — `cos_retrieve` current envelope; its doc already references "retrieval feedback" (line 111).
- **TASK-017** (J-2 dispatch layer selection / score normalisation, complete) — the router this tab's feedback loops into.
- **TASK-018** (J-3 retrieval router log migration, complete) — append-only log schema we already have; this task adds a *feedback* table alongside.
- [core/web/routes/search.py](../../core/web/routes/search.py) — same FastAPI pattern for the new route module.
- [docs/engineering/state-files.md](../../docs/engineering/state-files.md) — if we introduce new state, document it.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** the Retrieval tab is opened
  **When** it renders
  **Then** two panels show: **left** = a paginated list of recent `cos_retrieve` calls (query text, hint, chosen layer, result count, timestamp, agent), **right** = per-layer precision summary (memory / docs / tasks / graph / code-grep) as a horizontal bar with both raw counts and rolling-7d precision %.
- **Given** a selected retrieval entry
  **When** the drawer opens
  **Then** it shows: the full query, the dispatch score vector `(memory:0.42, docs:0.81, …)`, the layer chosen, the top 5 results returned, and two buttons 👍 Helpful / 👎 Not helpful. A free-form "why" text field is optional.
- **Given** the user submits feedback
  **When** the POST completes
  **Then** a row lands in the new `retrieval_feedback` SQLite table (migration vN+1, append-only — rule 9) with `{retrieve_id, feedback, reason, ts, agent}`. The right panel's precision bar refreshes within one second via SSE.
- **Given** a retrieval with no click-through and no feedback after 24 h
  **When** the nightly roll-up runs
  **Then** it is marked `implicit_negative` with lower weight (0.3× explicit feedback) — configurable.
- **Given** the Metrics tab (TASK-086)
  **When** it pulls the precision gauge
  **Then** the number comes from this table's 30-day rolling average.
- **Tests:** `tests/test_retrieval_feedback.py` covers migration, insert, precision aggregate, router integration; Playwright `e2e/retrieval-feedback.spec.ts` covers list + drawer + thumbs flow.

## Implementation Notes

1. **DB migration vN+1** (where N = current head) appending:
   ```sql
   CREATE TABLE retrieval_feedback (
     id INTEGER PRIMARY KEY,
     retrieve_id INTEGER NOT NULL,
     feedback TEXT CHECK (feedback IN ('helpful','not_helpful','implicit_negative')),
     reason TEXT,
     ts INTEGER NOT NULL,
     agent TEXT NOT NULL
   );
   CREATE INDEX ix_retrieval_feedback_retrieve_id ON retrieval_feedback(retrieve_id);
   ```
   Append-only — never edit older migrations.
2. **MCP tool:** `cos_retrieval_feedback(retrieve_id, feedback, reason=None) -> ok({id})` with proper envelope, `@safe_tool` wrap.
3. **Router integration:** TASK-017's `normalise_scores` already exposes a plug-in point for "historical precision"; feed the rolling per-layer precision as a bias term clipped to ±0.15 so we never collapse to one layer.
4. **UI:** `features/retrieval/RetrievalPage.tsx` + `<RetrievalList>` + `<FeedbackDrawer>`; respects existing design tokens.
5. **Privacy:** agent names only, never user identifiers; query text is stored but `/api/…` responses redact if the Settings flag `retrieval.redact_query` is true.
6. Tab feature-flagged by `hub-config.json::retrieval.enabled`.

## Dependencies

- **Depends on:** TASK-072 (feature flag), TASK-017 + TASK-018 (both already complete).
- **Unblocks:** TASK-086's precision gauge becomes live once feedback starts flowing.

## Work Log
