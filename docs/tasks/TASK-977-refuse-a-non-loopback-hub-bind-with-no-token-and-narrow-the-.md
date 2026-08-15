---
id: TASK-977
title: "Refuse a non-loopback Hub bind with no token, and narrow the Docker $HOME mount"
swimlane: core
kind: bug
epic: null
labels: [hub, hardening, P1, ready]
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
# TASK-977: Refuse a non-loopback Hub bind with no token, and narrow the Docker $HOME mount

**Outcome (one sentence):** Exposing the Hub beyond loopback without authentication becomes impossible by accident rather than merely discouraged in a doc.

## Read First
- src/core/web/security.py
- docs/engineering/hub-threat-model.md
- docker-compose.yml

## Repro Steps
security.py's own docstring states the hub is unauthenticated. Its auth block is guarded by `if token and ...`, so with COS_HUB_TOKEN unset and COS_WEB_HOST=0.0.0.0 the whole API — including the code graph — is served to the network with no credential and no startup refusal. docker-compose.yml bind-mounts $HOME read-only by default; SCAN_ROOT exists but is opt-in.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** COS_WEB_HOST resolves to a non-loopback address and COS_HUB_TOKEN is unset, **When** the server starts, **Then** it refuses with a message naming the fix.
- **Given** loopback with no token, **When** the server starts, **Then** behaviour is byte-unchanged.
- **Given** the default docker-compose, **When** it runs, **Then** it mounts the project root and requires an explicit opt-in to scan $HOME.

## Work Log
- 2026-08-14 [claude]: Fixed in 7dd9db33. Guard lives in create_app, not run_server, because uvicorn is pointed straight at the factory…
- 2026-08-14 [claude]: Status transitioned to complete via cos task-done.
- 2026-08-14 [claude]: Edit block-bad-patterns.sh
- 2026-08-14 [claude]: Edit test_hooks_stack_scoped_rules.py
- 2026-08-14 [claude]: Edit test_hooks_stack_scoped_rules.py
- 2026-08-14 [claude]: Edit msg11.txt
- 2026-08-14 [claude]: commit 89e40f4c68 — fix(hooks): scope the layered-backend rules to stacks that opted into them
- 2026-08-14 [claude]: Edit _config_adapters.py
- 2026-08-14 [claude]: Edit _config_adapters.py
- 2026-08-14 [claude]: Edit adapter.yaml
- 2026-08-14 [claude]: Edit roles.py
- 2026-08-14 [claude]: Edit roles.py
- 2026-08-14 [claude]: Edit presence_provider.py
- 2026-08-14 [claude]: Edit adapter.yaml
- 2026-08-14 [claude]: Edit _presence_runtime.py
- 2026-08-14 [claude]: Edit _cognition_chat_sdk.py
- 2026-08-14 [claude]: Edit adapter-parity.md
- 2026-08-14 [claude]: Edit msg12.txt
- 2026-08-14 [claude]: commit 5777193338 — fix(core): resolve the agent runtime through the adapter registry, not by SDK name
