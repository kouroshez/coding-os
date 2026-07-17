---
id: TASK-844
title: "Remove dead record_review writer + make cos_search auto-write the memory-check marker"
swimlane: "thinking_os"
kind: refactor
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
# TASK-844: Remove dead record_review writer + make cos_search auto-write the memory-check marker

**Outcome (one sentence):** Two memory-subsystem integrity fixes: (1) the never-invoked record_review.py writer (superseded by session_enrich's auto-facts + cos_learn_narrative's manual path) is removed so no dead duplicate writer of session_summaries lingers; (2) the Orient memory-check becomes a REAL signal — a live cos_search auto-writes the .memory-check marker, so enforce-memory-check reflects an actual query instead of an unverifiable self-attestation (manual self-attest stays a documented fallback).

## Read First
- docs/engineering/state-files.md
- src/core/thinking_os/record_review.py
- src/core/thinking_os/server.py
- src/core/hooks/enforce-memory-check.sh
- src/core/thinking_os/session_summary.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** record_review.py has zero production callers and its columns are written by session_enrich already **When** it and its test are removed and the dangling session_summary.py comment is fixed **Then** the thinking_os suite stays green (no orphaned import/reader).
**Given** an agent calls the MCP cos_search tool during Orient **When** the search returns **Then** the panel-dir .memory-check marker is written automatically (format cos_search:<query>), satisfying enforce-memory-check without a manual self-attest.
**Given** the shared panel/agent dir resolution **When** both _persist_learn_suggestions_safe and the new memory-check writer need it **Then** they call one shared helper, not two copy-pasted blocks.

## Work Log
- 2026-07-17 [claude]: Edit server.py
- 2026-07-17 [claude]: Edit server.py
- 2026-07-17 [claude]: Edit server.py
- 2026-07-17 [claude]: Edit session_summary.py
- 2026-07-17 [claude]: Edit state-files.md
- 2026-07-17 [claude]: Edit enforce-memory-check.sh
- 2026-07-17 [claude]: Edit verify_cluster4.py
- 2026-07-17 [claude]: Edit test_server.py
- 2026-07-17 [claude]: Verified: e2e (marker auto-write, shared helper resolution, learn-suggestions no-regress, record_review…
- 2026-07-17 [claude]: commit 78b6176d77 — refactor(thinking_os): drop dead record_review + auto-record memory-check on cos_search
