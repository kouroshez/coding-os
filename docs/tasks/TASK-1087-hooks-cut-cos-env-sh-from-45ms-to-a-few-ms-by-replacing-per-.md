---
id: TASK-1087
title: "Hooks: cut cos-env.sh from ~45ms to a few ms by replacing per-source forks with bash builtins"
swimlane: core
kind: refactor
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-10-25
started: 2026-10-25
completed: 2026-10-25
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1087: Hooks: cut cos-env.sh from ~45ms to a few ms by replacing per-source forks with bash builtins

**Outcome (one sentence):** Every hook in every project sources cos-env.sh and calls cos_log_hook without forking dirname/basename/printenv/cut/tr/grep/head/awk/date/mkdir/wc, so the per-hook floor drops from ~45ms of fork+exec to a few ms.

## Read First
- docs/playbooks/hook-authoring.md
- src/core/hooks/cos-env.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the old and new cos-env.sh sourced under `set -euo pipefail` on bash 5.3 and /bin/bash 3.2
- **When** a harness compares every exported COS_* variable, cos_current_session, cos_current_task and the cos_log_hook line across repo root, subdir, a consumer fixture (git_settings with an empty protected list, odd task-current spacing, .model file), codex env and ppid fallback, plus a disabled-hook-scripts hit
- **Then** outputs are identical, the measured source cost drops, and `make verify-hooks` + `tests/test_hooks_fail_closed.py` + `tests/test_golden_parity.py` pass

## Work Log
- 2026-10-25 [claude]: Measured: sourcing cos-env.sh cost 56ms vs 6ms for bare bash, all of it ~25 fork+exec calls; ~20 hooks source it per…
- 2026-10-25 [claude]: Status transitioned to complete via cos task-done.
