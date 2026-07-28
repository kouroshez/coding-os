---
id: TASK-628
title: "Persist + surface sub-agent raw_transcript from formula/role dispatch (currently dropped)"
swimlane: "thinking_os"
kind: feature
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-27
started: 2026-06-27
completed: 2026-06-27
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-628: Persist + surface sub-agent raw_transcript from formula/role dispatch (currently dropped)

**Outcome (one sentence):** A sub-agent's raw_transcript (already produced by the SDK dispatchers but dropped in cos_dispatch_formula_run) is persisted to the formula_dispatches table via an append-only migration and surfaced through `cos cognition trace`, so a founder can read the chat/session of a formula/role-dispatched sub-agent instead of only its summarized output_json.

## Read First
- src/core/thinking_os/tools/cognition.py
- src/core/thinking_os/database.py
- src/cli/cognition.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a formula/role dispatch produces a DispatchResult with a non-empty raw_transcript **When** cos_dispatch_formula_run records the dispatch **Then** the transcript (capped to a sane size) is stored in a new append-only column and is retrievable. - **Given** a recorded dispatch with a transcript **When** I run `cos cognition trace <session>` with the transcript flag **Then** the sub-agent transcript is shown. - **Given** an old dispatch row with no transcript **Then** the view degrades gracefully (no error).

## Work Log
- 2026-06-27 [claude]: Edit database.py
- 2026-06-27 [claude]: Edit database.py
- 2026-06-27 [claude]: Edit cognition.py
- 2026-06-27 [claude]: Edit cognition.py
- 2026-06-27 [claude]: Edit cognition.py
- 2026-06-27 [claude]: Edit cognition.py
- 2026-06-27 [claude]: Edit cognition.py
- 2026-06-27 [claude]: Edit cognition.py
- 2026-06-27 [claude]: Edit cognition.py
- 2026-06-27 [claude]: Edit cognition.py
- 2026-06-27 [claude]: Edit cognition.py
- 2026-06-27 [claude]: Edit cognition.py
- 2026-06-27 [claude]: Implemented: migration v44 adds formula_dispatches.raw_transcript (append-only, no index — never queried by content);…
- 2026-06-27 [claude]: Edit test-and-lifecycle-audit-2026-06.md
- 2026-06-27 [claude]: committed 1cb24c62 · 5 files
