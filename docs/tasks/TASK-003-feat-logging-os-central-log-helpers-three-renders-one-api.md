---
id: TASK-003
title: "feat(logging_os): central log helpers — three renders, one API"
swimlane: core
kind: feature
epic: null
labels: [logging, dx, core]
status: archive
priority: P2
appetite: "4h"
created: 2026-05-15
started: 2026-05-14
completed: 2026-05-14
agent_session: ses-claude-20260514-225105-3e2a
depends_on: []
blocked_by: []
references:
  - docs/engineering/logging_os.md
---
# TASK-003: feat(logging_os): central log helpers — three renders, one API

**Outcome (one sentence):** Ship `src/core/logging_os/` Python module plus `cos_say` shell helper that emit a single structured log schema rendered three ways (pretty for human TTY, short for agent/pipe, json for hub UI) with automatic context detection and zero new dependencies.

## Read First
- docs/engineering/logging_os.md — contract (written first under this task)
- src/core/hooks/cos-env.sh — `cos_log_hook` pattern + fail-open helpers
- src/core/rules/anti-overengineering.md — Rule 22 scope discipline
- src/core/rules/api-contract-discipline.md — producer is SSOT for field names

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a developer or hook calls `cos_log.warn("scope.name", "msg", file="x.py")` (Python) or `cos_say warn scope.name "msg" file=x.py` (shell)
- **When** the call runs in three contexts (TTY, piped, `COS_LOG_JSON=1`)
- **Then** the same event renders as pretty (TTY), short (pipe), or NDJSON (env), all three sinks fan out (stderr + `$COS_LOG_FILE` + `$COS_LOG_FILE.jsonl`), and tests assert byte-exact snapshots for each render mode
- **And** all unit tests in `src/core/logging_os/tests/` pass under `uv run pytest`
- **And** `make verify-hooks` passes after the `cos_say` append

## Work Log
- 2026-05-15 [claude]: Built src/core/logging_os/ — 5 files (config, render, sinks, api, __init__) ~340 LOC + 4 test files (test_render, test_detect, test_sinks, test_api) — 39/39 passing under `uv run pytest src/core/logging_os/tests/ -q`. Stdlib only, zero new deps.
- 2026-05-15 [claude]: Three pure renderers (pretty / short / json) auto-selected from detect_render() — env COS_LOG_JSON > COS_LOG_FORCE_PRETTY > NO_COLOR > isatty(stderr). Three sinks fan out per event: stderr (per-detect render), $COS_LOG_FILE text (always short), ${COS_LOG_FILE}.jsonl (always json — for hub UI / Loki ingest). Sinks fail-open (BrokenPipeError + OSError swallowed).
- 2026-05-15 [claude]: Public API five producer functions (ok / info / warn / error / fatal / debug) + scoped() pre-binder + Level enum + setup(). __all__ locked by test_api.test_public_surface_is_locked. Level.OK = 21 (not 20) to avoid IntEnum aliasing where Level.OK.name returned "INFO".
- 2026-05-15 [claude]: Shell parity via cos_say appended to src/core/hooks/cos-env.sh (~85 LOC) + src/core/hooks/_helpers/cos_say_json.py (24 LOC, used to escape JSON safely without bash heredoc-deadlock pattern). Same env detection, same level floor (COS_LOG_LEVEL), same three sinks, byte-exact short + json parity with Python verified.
- 2026-05-15 [claude]: Doc docs/engineering/logging_os.md (Rule 19 docs-first) — schema contract, render examples, env vars, channel discipline, scope naming convention, migration policy (new code only — no bulk rewrite, anti-overengineering).
- 2026-05-15 [claude]: pyproject.toml testpaths extended with src/core/logging_os/tests so future `uv run pytest` auto-discovers. Graph reindexed for src/core/logging_os/ (11 files) + src/core/hooks/_helpers/ (17 files).
- 2026-05-15 [claude]: `make verify-hooks` clean (bash -n + shellcheck warning level). Existing hooks (enforce-doc-anchor.sh, cos_log_hook) regression-tested — no break.
- 2026-05-15 [claude]: Status transitioned to complete via cos task-done.
