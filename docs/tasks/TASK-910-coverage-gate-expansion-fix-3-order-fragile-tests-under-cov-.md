---
id: TASK-910
title: "Coverage gate expansion: fix 3 order-fragile tests under --cov, fold tests/ into make coverage, ratchet fail_under 60-70-80"
swimlane: core
kind: test
epic: null
labels: [quality, ci, coverage, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-08-08
started: null
completed: null
agent_session: null
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
