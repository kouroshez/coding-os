# logging_os — Central Log Helpers

> One producer API. One schema. Three renders. Three sinks. Auto-detected context.
> Stdlib only. Agent-agnostic, stack-agnostic — lives in `src/core/logging_os/` (DNA layer).

## Purpose

Replace ad-hoc `print(...)`, `echo "warning: ..."`, and nine scattered `logging.basicConfig(...)` sites with a single helper that:

1. Speaks one structured schema every consumer understands (agent grep, human eyes, hub UI dashboard).
2. Picks the right render automatically from terminal context — no flag in 95% of calls.
3. Fans every event into the right channels at once (stderr + text log + json log) without forcing the producer to think about it.

This module is **not** a logging framework. It wraps stdlib `sys.stderr.write` plus `RotatingFileHandler` and exposes five functions. Total surface fits on one page.

## Event schema (the contract)

Every log event is the same dict, regardless of producer language:

| Field | Type | Required | Notes |
|---|---|---|---|
| `ts` | str | yes | ISO 8601 UTC (`2026-05-14T22:51:09Z`) |
| `lvl` | str | yes | `DEBUG` / `INFO` / `OK` / `WARN` / `ERROR` / `FATAL` |
| `scope` | str | yes | dotted snake (`cli.doctor`, `hook.enforce_skill`, `hub.routes.board`) |
| `msg` | str | yes | one line, human English, no trailing punctuation |
| `kv` | dict | no | flat string-keyed map of structured fields (`file=...`, `code=...`) |

**Field names are SSOT.** Hub UI, CI ingest, and tests must use these exact names — no renaming at any layer (per `src/core/rules/api-contract-discipline.md`).

## Three renders

### `pretty` — human TTY

```
ℹ️   22:51:09  INFO   cli.doctor          stack.category_balance check passed
✅  22:51:10  OK     cli.doctor          all 38 checks green
⚠️   22:51:11  WARN   hook.enforce_skill  graph-explorer not loaded  file=src/core/x.py
❌  22:51:12  ERROR  thinking_os.server  db migration v23 failed     code=DUPCOL
💀  22:51:13  FATAL  cli.main            uv not on PATH — abort
🔍  22:51:14  DEBUG  graph_os.indexer    upserted 14 nodes           file=foo.py
```

- emoji prefix from a fixed map
- ANSI color on the `lvl` token only
- `HH:MM:SS` timestamp (full ISO is verbose for humans)
- `scope` right-padded to a fixed column for vertical alignment
- `kv` tail joined as `key=value` with two-space lead-in

### `short` — agent / pipe / file

```
22:51:09 INFO  cli.doctor stack.category_balance check passed
22:51:10 OK    cli.doctor all 38 checks green
22:51:11 WARN  hook.enforce_skill graph-explorer not loaded file=src/core/x.py
22:51:12 ERROR thinking_os.server db migration v23 failed code=DUPCOL
22:51:13 FATAL cli.main uv not on PATH — abort
22:51:14 DEBUG graph_os.indexer upserted 14 nodes file=foo.py
```

- no emoji, no color, no padding
- single-space separated
- regex parsable: `^(\d{2}:\d{2}:\d{2}) (\w+)\s+(\S+) (.+?)( \w+=\S+)*$`

### `json` — hub UI / Loki / dashboards

```json
{"ts":"2026-05-14T22:51:11Z","lvl":"WARN","scope":"hook.enforce_skill","msg":"graph-explorer not loaded","file":"src/core/x.py"}
{"ts":"2026-05-14T22:51:12Z","lvl":"ERROR","scope":"thinking_os.server","msg":"db migration v23 failed","code":"DUPCOL"}
```

- one NDJSON object per line
- full ISO timestamp
- `kv` fields flattened to top-level keys

## Three sinks (fan-out per event)

| Sink | Render | Path | Purpose |
|---|---|---|---|
| stderr | per-detect | — | live human / agent capture |
| text file | always `short` | `$COS_LOG_FILE` (default `$COS_STATE_DIR/.cos.log`) | grep, `tail -f`, CI logs |
| jsonl file | always `json` | `$COS_LOG_FILE.jsonl` | hub UI, Loki, structured search |

Every `cos_log.<level>` call writes to all three. No producer-side selection. Sinks fail-open: a write error never propagates.

File sinks self-truncate: when a log file exceeds `COS_LOG_MAX_LINES × 2` lines (default 10000), the oldest half is dropped and the most recent `COS_LOG_MAX_LINES` is kept. No external rotation daemon needed.

## Render detection (per call, no caching)

```
1. COS_LOG_JSON=1                     → json
2. COS_LOG_FORCE_PRETTY=1             → pretty
3. NO_COLOR set                       → short
4. sys.stderr.isatty() is True        → pretty
5. otherwise                          → short
```

Detection runs at every emit so env changes (e.g. test harness toggling) take effect immediately.

## Channel discipline

| Channel | Carries | Why |
|---|---|---|
| `stdout` | command **data** (JSON dumps, table rows, query results) | pipeable by user / agent |
| `stderr` | log events (this module) | never collides with data; `command --json | jq` works |
| `$COS_LOG_FILE` | rolling history of all events | post-mortem, `cos hooks-log` |
| `$COS_LOG_FILE.jsonl` | machine ingest | hub UI / dashboards |

Producers calling `cos_log.warn(...)` write to stderr automatically. To emit data, use `print(...)` or `sys.stdout.write(...)` — those are not log calls.

## Producer API

### Python

```python
from core.logging_os import ok, info, warn, error, fatal, debug, scoped, setup, Level

setup(level="info")                               # idempotent; call once at entrypoint
                                                  # also installs stdlib logging bridge by default —
                                                  # any logger.X(...) record routes through cos_log dispatch

info("cli.doctor", "starting check sweep")
ok("cli.doctor", "all 38 checks green", count=38)
warn("hook.enforce_skill", "graph-explorer not loaded", file="src/core/x.py")
error("thinking_os.server", "db migration v23 failed", code="DUPCOL")
fatal("cli.main", "uv not on PATH — abort")        # also sys.exit(1)
debug("graph_os.indexer", "upserted nodes", count=14)

doctor_log = scoped("cli.doctor")                 # ergonomic pre-binding
doctor_log.warn("disk almost full", free_mb=120)
```

### Shell

```bash
source "$(dirname "$0")/cos-env.sh"

cos_say info  cli.doctor       "starting check sweep"
cos_say ok    cli.doctor       "all 38 checks green" count=38
cos_say warn  hook.enforce_skill "graph-explorer not loaded" file=src/core/x.py
cos_say error thinking_os.server "db migration v23 failed" code=DUPCOL
cos_say fatal cli.main         "uv not on PATH — abort"
```

`cos_say` is sourced from `cos-env.sh` alongside `cos_log_hook`.

## Levels

```
DEBUG (10) → development trace, silent unless COS_LOG_LEVEL=debug
INFO  (20) → narrative step
OK    (20) → successful completion (alias of INFO with green emoji)
WARN  (30) → recoverable problem, operation continues
ERROR (40) → operation failed, program continues
FATAL (50) → cannot continue; emits then exits 1
```

Level filter is a single floor: events below `COS_LOG_LEVEL` (default `info`) are dropped at the API layer before any render or sink.

## Environment variables

| Name | Default | Effect |
|---|---|---|
| `COS_LOG_LEVEL` | `info` | floor: one of `debug`, `info`, `warn`, `error`, `fatal` |
| `COS_LOG_JSON` | unset | `1` forces json render on stderr |
| `COS_LOG_FORCE_PRETTY` | unset | `1` forces pretty even when piped (debug aid) |
| `COS_LOG_FILE` | `$COS_STATE_DIR/.cos.log` | text sink path; `.jsonl` is appended for the json sink |
| `COS_LOG_SCOPE_WIDTH` | `20` | pretty-mode column width for `scope` |
| `COS_LOG_MAX_LINES` | `5000` | per-file line cap; truncates to last N when file exceeds 2× cap |
| `NO_COLOR` | unset | W3C standard — any value disables ANSI |

## Module layout (`src/core/logging_os/`)

```
__init__.py    # re-export public API only
api.py         # 6 producer functions + scoped()
render.py      # 3 pure renderers + EMOJI/COLOR maps
sinks.py       # fan-out writer (stderr + text file + jsonl file)
config.py      # Level enum, env vars, detect_render(), setup(), normalize_scope()
README.md      # one-page reference (mirror of this doc, condensed)
tests/
  test_api.py      # public surface + level filter
  test_render.py   # byte-exact snapshots per (level × render)
  test_detect.py   # detection matrix
  test_sinks.py    # fan-out + fail-open + rotation
```

`cos_say` lives in `src/core/hooks/cos-env.sh` (one helper, ~30 lines), so every hook that already sources `cos-env.sh` gets it for free.

## Scope naming convention

Dotted snake, mirrors repo path:

| Path | Scope |
|---|---|
| `src/cli/doctor.py` | `cli.doctor` |
| `src/cli/board_commands.py` | `cli.board` |
| `src/core/thinking_os/server.py` | `core.thinking_os.server` |
| `src/core/graph_os/indexer.py` | `core.graph_os.indexer` |
| `src/core/hooks/enforce-skill.sh` | `hook.enforce_skill` |
| `src/adapters/claude/install.sh` | `adapter.claude.install` |
| `src/core/web/routes/board.py` | `hub.routes.board` |

`config.normalize_scope()` validates: lowercase, `[a-z0-9_.]` only, ≤ 40 chars, ≥ 1 dot. Invalid scopes degrade to `"invalid.scope"` with the original kept under `kv["raw_scope"]`.

## What does NOT belong here

| Concern | Where it lives | Hub UI consumer |
|---|---|---|
| MCP tool error envelope (`ok`/`fail`) | `src/core/thinking_os/tools/_shared.py` (Rule 13) | — (wire only) |
| Hook activity log (`cos_log_hook`) | `src/core/hooks/cos-env.sh` → `.coding-os/.hooks.log` | Observability tab → Hook stream |
| Cognition trace JSONL | `src/core/thinking_os/tracing.py` → `.coding-os/<agent>/traces/<session>.jsonl` | Cognition tab |
| Per-task work log (`cos work-log-append`) | `src/core/board_os/` | Board tab |
| Multi-line UX banners in hooks (e.g. warn-mcp-down repair instructions) | hook scripts (plain `echo` to stderr) | rendered live to terminal |

These each have different consumers and lifetimes. logging_os is for **operational narration** by humans / agents / dashboards.

## Hub UI consumer

- `/api/logs/recent` — tail of `.cos.log.jsonl`; query params: `level` (debug..fatal floor), `scope` (fnmatch glob), `search` (substring on msg), `since` (relative duration: 30s, 10m, 1h, 2d), `limit` (1..2000).
- `/api/logs/stream` — SSE; emits one `log` event per new line plus periodic `heartbeat`; supports the same `level` / `scope` / `search` filters.
- React route `/logs` (global) and `/p/:slug/logs` (project-scoped) — filter bar + table + live tail toggle.

The Logs tab is for application narration (Python `logger.X(...)` records routed through the bridge, plus direct `cos_log` / `cos_say` calls). For hook fire activity use the Observability tab; for cognitive routing decisions use the Cognition tab.

## Stdlib logging bridge

`setup()` installs a `LoggingOsHandler` on the root logger by default. Any module that already uses `logging.getLogger(__name__).info(...)` automatically routes through cos_log dispatch — same renders, same sinks, same level filter. No call-site change needed.

- Logger name → scope: `core.thinking_os.server` stays as-is; `__main__` becomes `py.main`; dashes become underscores; an undotted name gets a `py.` prefix.
- Record level → cos level: `DEBUG → DEBUG`, `INFO → INFO`, `WARNING → WARN`, `ERROR → ERROR`, `CRITICAL → FATAL`.
- Disable with `setup(install_stdlib_bridge=False)` only when a process needs to keep its own root handlers (rare; nightly cron keeps a `RotatingFileHandler` *alongside* the bridge — both fire).

`uninstall_bridge()` is exposed for tests and shutdown paths.

## Migration policy

1. **New code** — use `cos_log.*` (Python) or `cos_say` (shell). No exceptions.
2. **Server-side `logging.basicConfig(...)`** — replaced repo-wide with `cos_log.setup(...)`; the stdlib bridge keeps every existing `logger.X(...)` call working unchanged.
3. **Existing `print()` / `echo`** in CLI scripts and dev helpers — leave alone unless touching the file for another reason. Bulk rewrite is forbidden (anti-overengineering, Rule 22).
4. **Doctor (`cli.doctor`)** — owns its report formatter (PASS/WARN/FAIL badges); stays as-is. Doctor uses `cos_log` only for log events that surround the report.
5. **MCP envelope** — never replaced. `fail("validation", "...")` is the wire contract; logging is the narration.

## Verification

| Changed | Command |
|---|---|
| `src/core/logging_os/**` | `uv run pytest src/core/logging_os/tests/ -q` |
| `src/core/hooks/cos-env.sh` | `make verify-hooks` |

Manual smoke tests (the three renders):

```bash
# pretty (TTY)
python3 -c "from core.logging_os import warn; warn('manual.test', 'pretty render', file='x.py')"

# short (pipe)
python3 -c "from core.logging_os import warn; warn('manual.test', 'short render', file='x.py')" 2>&1 | cat

# json (env)
COS_LOG_JSON=1 python3 -c "from core.logging_os import warn; warn('manual.test', 'json render', file='x.py')"
```

## Anti-patterns

- `print("WARN: ...")` in CLI — use `cos_log.warn`.
- `echo "[error] ..." >&2` in a hook — use `cos_say error <scope> "..."`.
- `import logging; logging.basicConfig(...)` in a new module — call `cos_log.setup()` at the entrypoint instead.
- Custom emoji or color per call — the maps in `render.py` are SSOT.
- Writing log lines to `stdout` — breaks `--json` parsers.
- Multi-line log messages — use single line + `kv` fields. Stack traces are the only allowed continuation (two-space indent).

## See also

- `src/core/rules/api-contract-discipline.md` — producer is the source of truth for field names.
- `src/core/rules/anti-overengineering.md` — why this module is five files, not fifteen.
- `src/core/hooks/cos-env.sh` — `cos_log_hook` (hook telemetry, separate concern).
- `docs/engineering/mcp-error-envelope.md` — the wire contract that complements logs.
