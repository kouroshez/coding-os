---
id: TASK-910
title: "Coverage gate expansion: fix 3 order-fragile tests under --cov, fold tests/ into make coverage, ratchet fail_under 60-70-80"
swimlane: core
kind: test
epic: null
labels: [quality, ci, coverage, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-08
started: 2026-08-08
completed: 2026-08-08
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-910: Coverage gate expansion: fix 3 order-fragile tests under --cov, fold tests/ into make coverage, ratchet fail_under 60-70-80

**Outcome (one sentence):** make coverage runs src suites + tests/ deterministically under pytest-cov and fail_under ratchets from the src/core baseline toward 80

## Read First
- docs/engineering/test-governance.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** make coverage including tests/\n- **When** run twice consecutively\n- **Then** identical pass/fail result, test_cost_health_fails_open_without_db + TestCosEnv::test_db_path_follows_state_dir + test_claude_auth_env_api_key_mode pass under --cov, and fail_under is raised to the measured combined total (63% baseline measured 2026-08-08)

## Work Log
- 2026-08-08 [claude]: Edit test_hooks.py
- 2026-08-08 [claude]: Edit test_session_options_parity.py
- 2026-08-08 [claude]: Edit test_cognition_routes.py
- 2026-08-08 [claude]: Edit Makefile
- 2026-08-08 [claude]: Edit pyproject.toml
- 2026-08-08 [claude]: Root cause: ambient COS_DB_PATH/COS_STATE_DIR leakage (tests inherited os.environ). Hardened 3 tests hermetically…
- 2026-08-08 [claude]: Edit ci.yml
- 2026-08-08 [claude]: commit ecdd03896a — test(coverage): fold the root suite into the coverage gate, fail_under 62
- 2026-08-08 [claude]: Status transitioned to complete via cos task-done.
