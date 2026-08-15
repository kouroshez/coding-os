---
id: TASK-975
title: "Label stacks without real toolchain CI as experimental until they are proven"
swimlane: templates
kind: chore
epic: null
labels: [stacks, honesty, P1, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-14
started: 2026-08-14
completed: 2026-08-14
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-975: Label stacks without real toolchain CI as experimental until they are proven

**Outcome (one sentence):** A user reading the stack list can tell which stacks CI actually builds and tests, so "27 stacks" stops implying 27 verified stacks.

## Work Log
- 2026-08-14 [claude]: Fixed in 49da33dc. Chose to DERIVE maturity from scaffold-verify.yml rather than add a status field to 27 stack.yaml…
- 2026-08-14 [claude]: Status transitioned to complete via cos task-done.
- 2026-08-14 [claude]: Edit security.py
- 2026-08-14 [claude]: Edit server.py
- 2026-08-14 [claude]: Edit docker-compose.yml
- 2026-08-14 [claude]: Edit docker-compose.yml
- 2026-08-14 [claude]: Edit docker-compose.yml
- 2026-08-14 [claude]: Edit docker-compose.yml
- 2026-08-14 [claude]: Edit test_hub_bind_guard.py
- 2026-08-14 [claude]: Edit hub-threat-model.md
- 2026-08-14 [claude]: commit 7dd9db3343 — fix(hub): refuse an off-loopback bind with no token, stop mounting all of $HOME
