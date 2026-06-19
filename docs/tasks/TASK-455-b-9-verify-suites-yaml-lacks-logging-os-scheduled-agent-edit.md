---
id: TASK-455
title: "B-9: verify-suites.yaml lacks logging_os + scheduled \u2014 agent edits get zero matrix gate (F-TST-1)"
swimlane: "board_os"
kind: chore
epic: null
labels: [modularity-audit-pass3, F-TST-1, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-19
started: 2026-06-19
completed: 2026-06-19
agent_session: ses-claude-20260619-063923-1c50
depends_on: []
blocked_by: []
references: []
---
# TASK-455: B-9: verify-suites.yaml lacks logging_os + scheduled — agent edits get zero matrix gate (F-TST-1)

**Outcome (one sentence):** src/core/logging_os/**/*.py and src/core/scheduled/**/*.py — both shipped runtime in CI on every PR — now map to a verify suite in src/core/board_os/verify-suites.yaml (the SSOT the enforce-verify hook + DoD gate read). Before: match_suites returned [] for these dirs so cmd_check returned ALLOW and a completion recorded no PASS/FAIL, the same blind spot that let the 2 prior CI-hidden REDs land. New test-logging_os + test-scheduled suites mirror the CI subsystem commands.

## Work Log
- 2026-06-19 [claude]: Edit verify-suites.yaml
- 2026-06-19 [claude]: Edit record-verify-auto.sh
- 2026-06-19 [claude]: committed eddb14e7 · 2 files
- 2026-06-19 [claude]: Edit main.py
- 2026-06-19 [claude]: Edit main.py
- 2026-06-19 [claude]: Edit main.py
- 2026-06-19 [claude]: Edit main.py
- 2026-06-19 [claude]: Edit test_init_dry_run_preview.py
- 2026-06-19 [claude]: Edit test_init_dry_run_preview.py
