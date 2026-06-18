---
id: TASK-447
title: "Modularity test legibility: fast PR-gated toggle round-trips (F7) + shell\u2192log_events BLOCK bridge (F8)"
swimlane: infra
kind: feature
epic: null
labels: [modularity, audit-2026-06, tests, observability, F7, F8, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-18
started: 2026-06-18
completed: 2026-06-18
agent_session: ses-claude-20260617-183518-6ce2
depends_on: []
blocked_by: []
references: []
---
# TASK-447: Modularity test legibility: fast PR-gated toggle round-trips (F7) + shell→log_events BLOCK bridge (F8)

**Outcome (one sentence):** A modularity regression is caught on the PR that causes it and is legible to an agent: module/stack toggle round-trips run fast on every PR (not nightly-only), and a hook BLOCK leaves a machine-readable row in log_events that cos_log_query surfaces.

## Read First
- tests/test_cli.py
- tests/test_remove_stack.py
- .github/workflows/ci.yml
- src/core/hooks/cos-env.sh
- src/core/logging_os/sinks.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the deterministic toggle assertions (module/stack: section dropped, skill unlinked, allowlist joined, byte-identical restore) currently behind a module-level @slow mark (F7) **When** they are extracted into non-slow variants **Then** they run in the test-modularity PR job and fail a breaking PR without waiting for the nightly schedule.

**Given** a hook BLOCK or WARN fires (F8) **When** it logs **Then** a single shell→DB writer records a row into the SQLite log_events store (the sink Python owns) so cos_log_query / error_sweep surface it — consolidating the two duplicate shell paths (cos_log_hook + cos_say).

**Given** a consumer toggles a module off and an edit is then mysteriously blocked **When** the agent runs cos_log_query **Then** the BLOCK is visible with the module/hook that caused it.

**Given** these changes **When** make verify-hooks + uv run pytest tests/test_cli.py + the logging_os suite run **Then** they pass.

## Work Log
- 2026-06-18 [claude]: Edit test_modularity_toggle.py
- 2026-06-18 [claude]: Edit test_cli.py
- 2026-06-18 [claude]: Edit ci.yml
- 2026-06-18 [claude]: commit 0bd8c6bd6d — test(modularity): fast PR-gated toggle round-trips run on every PR (F7)
- 2026-06-18 [claude]: Edit cos_say_json.py
- 2026-06-18 [claude]: Edit cos-env.sh
- 2026-06-18 [claude]: Edit f8_smoke.py
- 2026-06-18 [claude]: Edit f8_smoke.py
- 2026-06-18 [claude]: Edit test_cos_say_db_bridge.py
- 2026-06-18 [claude]: Edit logging_os.md
- 2026-06-18 [claude]: commit aa5a7351d1 — feat(modularity): hook BLOCK/WARN durable in log_events, not just the tail (F8)
- 2026-06-18 [claude]: F7 LANDED (0bd8c6bd): moved subprocess-free toggle round-trips out of test_cli.py module-level @slow into…
- 2026-06-18 [claude]: F8 LANDED (aa5a7351): cos_say_json.py is now the single shell→DB writer — cos_say(WARN+) + cos_log_hook block insert…
- 2026-06-18 [claude]: Status transitioned to complete via cos task-done.
