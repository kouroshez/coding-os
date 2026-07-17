---
id: TASK-846
title: "Atomic write-path dedup \u2014 partial UNIQUE(content_hash, session_id) + INSERT OR IGNORE"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-07-17
started: 2026-07-17
completed: 2026-07-17
agent_session: ses-claude-20260717-014556-89d0
depends_on: []
blocked_by: []
references: []
---
# TASK-846: Atomic write-path dedup — partial UNIQUE(content_hash, session_id) + INSERT OR IGNORE

**Outcome (one sentence):** Observation capture can no longer create duplicate rows under a race: the existing (content_hash, session_id) dedup is enforced atomically by a partial UNIQUE index + INSERT OR IGNORE, instead of a race-prone SELECT-then-INSERT where two concurrent captures both miss the SELECT and both insert. Historical duplicates are collapsed once by migration v51 (keeping the earliest row).

## Read First
- src/core/thinking_os/database.py
- src/core/thinking_os/capture.py
- docs/engineering/learning-extraction.md

## Repro Steps
capture.py:347-353 SELECTs for an existing (content_hash, session_id) observation and only INSERTs if none found — but the SELECT and INSERT are not atomic. Two PostToolUse captures of the same (tool, file) in the same session that interleave both pass the SELECT (neither committed yet) and both INSERT, producing duplicate observation rows (a contributor to the corpus noise). No UNIQUE constraint exists on observations(content_hash, session_id).

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** existing duplicate observations sharing (content_hash, session_id) **When** migration v51 runs **Then** only the earliest id per group survives and a partial UNIQUE index on (content_hash, session_id) WHERE both non-NULL exists; the observations_fts index stays consistent (DELETE trigger) and no FK breaks (none reference observations.id).
**Given** two captures of the same (tool, file, session) racing past the SELECT **When** both reach the INSERT OR IGNORE **Then** exactly one row exists and the race-loser returns status=deduped without running post-insert graph/embedding work on a bogus lastrowid.
**Given** a NULL content_hash or NULL session_id observation **When** it is inserted **Then** the partial index does not constrain it (multiple allowed) — non-dedup rows are unaffected.

## Work Log
- 2026-07-17 [claude]: Edit database.py
- 2026-07-17 [claude]: Edit database.py
- 2026-07-17 [claude]: Edit capture.py
- 2026-07-17 [claude]: Edit verify_cluster3.py
- 2026-07-17 [claude]: Edit test_db.py
- 2026-07-17 [claude]: Verified: e2e (schema v51 + partial unique index; INSERT OR IGNORE race-loser rowcount=0 → 1 row; NULL…
