---
id: TASK-016
title: "fix capture-observation MultiEdit drop"
swimlane: core
kind: bug
epic: null
labels: [memory, observability]
status: archive
priority: P1
appetite: "1h"
created: 2026-05-23
started: 2026-05-23
completed: 2026-05-23
agent_session: ses-claude-20260523-010526-e647
depends_on: []
blocked_by: []
references:
  - src/core/hooks/capture-observation.sh
  - src/core/thinking_os/capture.py
---
# TASK-016: fix capture-observation MultiEdit drop

**Outcome (one sentence):** PostToolUse MultiEdit calls produce observation rows in `observations` table — currently dropped at shell filter despite Python layer supporting them.

## Read First
- [src/core/hooks/capture-observation.sh](../../src/core/hooks/capture-observation.sh) — shell hook with the bug at line 28
- [src/core/thinking_os/capture.py](../../src/core/thinking_os/capture.py) — Python layer (CAPTURE_TOOLS already includes MultiEdit, line 31)

## Repro Steps
1. Run a session where the agent issues a MultiEdit on any file under repo.
2. `tail .coding-os/.hooks.log | grep capture-observation` — fire entry appears with `tool=MultiEdit`.
3. Wait for session end, `sqlite3 .coding-os/coding-os.db "SELECT COUNT(*) FROM observations WHERE created_at > datetime('now','-1 hour');"` returns 0.

Expected: ≥1 row per MultiEdit call. Actual: 0 rows; shell filter at `capture-observation.sh:28` exits before spawning `capture.py`.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the agent issues a MultiEdit tool call on any file
- **When** the PostToolUse hook fires `capture-observation.sh`
- **Then** the shell case-pattern matches `MultiEdit`, `capture.py` is spawned, and a new row appears in `observations` within ≤2s of the call. `make verify-hooks` passes.

## Work Log
- 2026-05-23 — diagnosed shell-vs-python filter mismatch, patched `capture-observation.sh:28` to include MultiEdit, smoke-tested via direct capture.py and shell-hook paths (observations rows #3 + #4 written), `make verify-hooks` clean, committed `9dca67a`.
- 2026-05-23 [claude]: Status transitioned to complete via cos task-done.
