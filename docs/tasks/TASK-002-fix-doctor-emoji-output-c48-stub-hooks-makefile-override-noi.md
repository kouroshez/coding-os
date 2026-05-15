---
id: TASK-002
title: "fix(doctor): emoji output + C48 stub hooks + Makefile override noise + C32 message"
swimlane: cli
kind: bug
epic: null
labels: []
status: complete
priority: P2
appetite: "2h"
created: 2026-05-15
started: 2026-05-15
completed: 2026-05-14
agent_session: ses-claude-20260514-225105-3e2a
depends_on: []
blocked_by: []
references: []
---
# TASK-002: fix(doctor): emoji output + C48 stub hooks + Makefile override noise + C32 message

**Outcome (one sentence):** All `cos doctor` output and install scripts use ✅/⚠️/❌ emoji badges; C48 WARNs on the two stub hooks are cleared; Makefile override noise is suppressed; C32 message shows the correct fix command.

## Read First
- src/cli/doctor.py — _format_text() at line 1732
- src/core/hooks/doc-sync-reminder.sh — stub missing cos-env.sh source
- src/core/hooks/verify-changed-file.sh — stub missing cos-env.sh source
- src/templates/_base/Makefile.base — cron-install/verify targets that conflict with root Makefile
- src/cli/doctor_extras.py — C32 fix message at line 59

## Repro Steps
1. Run `cos doctor` — output uses [PASS]/[WARN]/[FAIL] text badges instead of emoji
2. C48 shows 2 violations: doc-sync-reminder.sh, verify-changed-file.sh
3. `make sync` emits "override" warnings from make for cron/verify targets
4. C32 WARN says "uv sync --all-extras" but global tool needs "uv tool install --editable . --all-extras"
Expected: emoji badges, zero C48 violations, no override warnings, correct C32 fix hint
Actual: text badges, 2 C48 violations, override warnings, ambiguous C32 fix

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `cos doctor` runs
- **When** all checks complete
- **Then** output uses ✅/⚠️/❌ badges, C48 PASS, no Makefile override noise, C32 message contextual

## Work Log
- 2026-05-15: fixed doc-sync-reminder.sh and verify-changed-file.sh (cos-env.sh source added); adding emoji to doctor.py _format_text
- 2026-05-15 [claude]: Status transitioned to complete via cos task-done.
