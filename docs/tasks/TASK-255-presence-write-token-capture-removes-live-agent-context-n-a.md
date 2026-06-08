---
id: TASK-255
title: "presence_write token-capture (removes live-agent context N/A)"
swimlane: core
kind: feature
epic: kernel-overrides
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260608-024900-f2b0
depends_on: []
blocked_by: []
references: []
---
# TASK-255: presence_write token-capture (removes live-agent context N/A)

**Outcome (one sentence):** Stamp per-turn token usage into sessions/<sid>.json from the Stop payload so live-agent context percent is real, not N/A.

## Read First
- src/core/hooks/_helpers/presence_write.py — where the session JSON is written.
- src/core/web/routes/presence.py — `_context_pct_from_usage` + how context_pct is read (currently tails the opt-in transcript).
- src/core/hooks/snapshot-transcript.sh — the COS_SNAPSHOT_TRANSCRIPT=1 gate (why context is N/A by default).

## Context / Approach
Add a context_pct / used_tokens field to sessions/<sid>.json stamped from the Claude Stop payload usage block, so presence.py reads it directly instead of tailing the privacy-gated transcript. Fail-open (presence is UX, not correctness). This is the ONE producer-side hook change in the epic and lands on the hot Stop path — verify with make verify-hooks + the board_os presence tests; do NOT bundle with UI work.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a Claude Stop with a usage block, **When** processed, **Then** presence.context_pct is non-null.
- **Given** a Stop with no usage block, **When** processed, **Then** it fails open (context stays "not tracked", no crash).

## Work Log
- 2026-06-08 [claude]: Stop-path captures used_tokens from live transcript into sessions/<sid>.json; presence.py derives real context_pct (hone
