# Observability Eye — Enterprise Error & Log Pipeline

> Nothing breaks unseen. Every error is captured, made durable, kept queryable, and — when it recurs — auto-filed as a board bug the agent can pull and fix.
> Built **on** `logging_os` (the producer facade). This doc specifies the nervous system *around* it: durable store, query surfaces, doctor visibility, and the error→bug-task loop.
> Agent-agnostic, stack-agnostic (DNA layer). SSOT for the `observability-eye` epic (TASK-101).

## Why — the gap this closes

`logging_os` is a complete producer (6 levels, `scoped()`, stdlib bridge, 3 renders, 3 sinks). The 2026-06-05 audit found it wired to almost nothing — a camera with no recorder:

- **Capture** — 9 Python importers, **0** `cos_say` hooks. The `cos` CLI and the web/hub FastAPI server never install the stdlib bridge, so every `cos doctor` error and every web-route 500 is invisible to the log meant to record it. ~429 silent `except` handlers (41.8% of first-party) route nothing through the eye.
- **Durability** — `WARN+`/`ERROR`/`FATAL` land only in a 5000-line rolling jsonl tail (`sinks.py` self-truncates, dropping the oldest half); an error from an hour ago is gone before anyone queries it.
- **Query** — no `cos_log_query` MCP tool, no `cos errors` CLI, no `cos doctor` check reads the sink. The system cannot answer *"what is broken right now"*.
- **Pipeline** — no error→bug-task path (greenfield).
- **Security inversion** — `branch-guard.sh` and `detect-exhaustive-intent.sh` **fail OPEN** when their helper crashes (stderr → `/dev/null`): a guard that silently stops guarding.

The eye is an **adoption + durability** program, not a rewrite. Every component below reuses existing machinery: the `logging_os` facade, `coding-os.db` append-only migrations, the `audit_log_query` query pattern, `scheduled/nightly.py`, `cli/doctor.py`, and the board.

## Architecture — data flow

```
PRODUCERS                         EYE (logging_os)          STORE                       SURFACES
─────────                         ────────────────          ─────                       ────────
python  except ─cos_log.error(exc=)┐                    ┌ jsonl tail (HOT, capped) ──── web Logs + SSE stream
hooks   shell  ─cos_say error──────┤   _emit            │   (debug/info live here)
mcp     fail() ────────────────────┼─► +redact   ─► sinks┤
cli/web 500    ─stdlib bridge──────┤   +trace_id          │ log_events DB (COLD, v32) ─┬ cos_log_query  (MCP)
nightly sweep  ─(reads store)──────┘   +stack             │   (WARN+, indexed, retained)  ├ cos errors     (CLI)
                                                          │                            ├ cos doctor runtime check
                                                          └ log_fingerprints (rollup) ─┴ nightly error-sweep
                                                                                          ├ FATAL    → emergency bug task
                                                                                          └ ERROR≥N  → icebox bug task
                                                                                             └─ agent pulls → fixes → archive
```

| Component | Module | Status (2026-06-05) | Change needed |
|---|---|---|---|
| Producer facade | `src/core/logging_os/` | exists | add `error(exc=)`, redaction, trace/session stamping, `swallow_safe()`; fix `fatal()` worker-kill |
| Stdlib bridge install | `web/server.py`, `cli/main.py`, MCP `server.py` | partial | one-line `setup()` per process (E1) |
| Durable store | `coding-os.db` | missing | migration **v32**: `log_events` + `log_fingerprints` (E2) |
| WARN+ DB sink | `logging_os/sinks.py` | missing | gated insert + fallback chain + `dropped_events` (E3) |
| MCP query | `thinking_os/tools/` | missing | `cos_log_query` ≈ clone of `audit_log_query` (E4) |
| CLI query | `cli/` | missing | `cos logs` / `cos errors` (E5) |
| Security guards | `hooks/branch-guard.sh`, `detect-exhaustive-intent.sh` | **broken (fail-open)** | fail CLOSED + capture helper stderr (E6) |
| Doctor visibility | `cli/doctor.py` | missing | `runtime.recent_errors` check (E7) |
| MCP envelope gaps | `board_os/mcp_tools.py` | partial | `@safe_tool` on `cos_task_show`/`cos_task_move` (E8) |
| Web Errors UI | `web/routes/logs.py`, `ui/` | partial | `/api/logs/summary` + Errors view + error-aware alarm bar (E11) |
| Error→bug sweep | `scheduled/nightly.py` | missing | 5th gated task (E12) |
| Capture adoption | repo-wide | ~5% | exhaustive handler conversion, coord TASK-100 (E13) |

## 1. Capture discipline — no silent failures (the law)

Every error path in the repo routes through the eye. Per producer surface:

- **Python** — never `except: pass` on a real error path. Use `logging_os.error(scope, msg, exc=e)` (captures stack), or for genuine fire-and-forget use `logging_os.swallow_safe(scope)` (logs `debug` + increments a counter) — never a bare swallow. The 3 bare `except:` are removed. Legit fire-and-forget keeps the Rule-6 `_*_safe()` shape but logs.
- **Shell / hooks** — `cos_say error <scope> <msg>` for real failures; a shared `cos_hook_error` trap in `cos-env.sh` captures unexpected hook deaths. `2>/dev/null` allowed only for *optional probes* (`command -v X`), never to hide a load-bearing op's stderr. Fail-closed hooks (security/enforcement) capture the crash before denying.
- **MCP** — every `cos_*` returns `fail(category, msg)` via `@safe_tool`; the decorator's `internal` path logs via `logger.exception` (now bridge-captured). No tool returns `ok()` on a caught error.
- **CLI / web** — both processes install the bridge at entry, so stdlib `logger.error`/uncaught 500s reach the eye.

**Severity → durability gate:** `DEBUG`/`INFO`/`OK` stay jsonl-tail-only (hot path, never touch the DB). `WARN`/`ERROR`/`FATAL` additionally persist to `log_events` (cold, durable).

## 2. Durable store — migration v32

Append-only entry in `thinking_os/database.py::MIGRATIONS` (latest is v31; **never edit a past migration** — Rule 9). `coding-os.db` is the single canonical store (`COS_DB_PATH`); no new DB, no ring buffer (Rule 22).

```sql
-- v32: durable error system-of-record (WARN+ only)
CREATE TABLE log_events (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  ts           TEXT NOT NULL,            -- ISO8601 UTC (event time)
  lvl          TEXT NOT NULL,            -- WARN | ERROR | FATAL
  scope        TEXT NOT NULL,            -- dotted snake (cli.doctor, hook.branch_guard)
  msg          TEXT NOT NULL,
  kv           TEXT,                     -- JSON object (flat, redacted)
  exc_type     TEXT,                     -- exception class, if any
  stack        TEXT,                     -- truncated traceback summary
  session_id   TEXT,                     -- join key → traces/<session>.jsonl
  trace_id     TEXT,
  fingerprint  TEXT NOT NULL,            -- sha1(scope|exc_type|msg_normalized)[:16]
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX idx_log_events_fp  ON log_events(fingerprint);
CREATE INDEX idx_log_events_ts  ON log_events(ts);
CREATE INDEX idx_log_events_lvl ON log_events(lvl);

-- permanent aggregate — survives raw-row pruning, idempotency anchor for the sweep
CREATE TABLE log_fingerprints (
  fingerprint        TEXT PRIMARY KEY,
  scope              TEXT NOT NULL,
  exc_type           TEXT,
  sample_msg         TEXT NOT NULL,
  max_lvl            TEXT NOT NULL,      -- highest severity ever seen
  first_seen         TEXT NOT NULL,
  last_seen          TEXT NOT NULL,
  count              INTEGER NOT NULL DEFAULT 0,
  distinct_sessions  INTEGER NOT NULL DEFAULT 0,
  task_id            TEXT,               -- board bug task once filed (idempotency)
  status             TEXT NOT NULL DEFAULT 'open'  -- open | filed | archived
);
```

**Fingerprint normalization** (so identical errors group into one task): lowercase `msg`; replace digits → `#`, hex/uuid runs → `<id>`, absolute paths → `<path>`; collapse whitespace. `fingerprint = sha1(scope + "|" + (exc_type or "") + "|" + msg_normalized)[:16]`.

**Retention (age × level):** keep `ERROR`/`FATAL` raw rows `COS_LOG_RETENTION_ERROR_DAYS` (default 30), `WARN` `COS_LOG_RETENTION_WARN_DAYS` (default 7). The nightly sweep computes the `log_fingerprints` rollup **before** pruning, so aggregate history (count/first/last) survives even when raw rows go. ⇒ *"no rows" provably means "no errors", not "aged out".*

## 3. Query surfaces

- **`cos_log_query` (MCP)** — `@safe_tool`, `meta.layer="logs"`. Modeled on `tools/audit.py::audit_log_query` (same WHERE-builder + `total`/`rows` shape). Filters: `level` floor, `scope` glob, `since`, `search` (indexed `LIKE` on `msg`; FTS5 deferred — WARN+ rows are low-volume, Rule 22), `session_id`/`trace_id`, `fingerprint`. This is how the agent asks *"what is broken right now"*.
- **`cos errors` / `cos logs` (CLI)** — human + agent-CLI access; reuses `render.py` for formatting; `cos errors --since 1h --level error`.
- **`cos doctor` runtime check** — `runtime.recent_errors`: WARN/FAIL when the `WARN+` rate in a window crosses a threshold; feeds the CI exit code so a project actively throwing errors can no longer report `exit=0 healthy`.
- **Web** — `/api/logs/recent` (existing, repointed to the DB) + `/api/logs/summary` (counts-by-level + top scopes) + SSE live stream; Hub **Errors** view with count rollup + session filter + an "open as bug" affordance; `HealthAlarmBar` turns red on an error storm.

## 4. Error → bug-task pipeline (nightly sweep, Task E12)

Hosted as a 5th gated task in `scheduled/nightly.py::run_project` (already runs daily under `flock` + auto-disable). Idempotent, dedup-first:

```
1. Upsert log_fingerprints from new log_events (count, last_seen, distinct_sessions, max_lvl).
2. For each fingerprint where status == 'open':
     if max_lvl == FATAL:                        → create EMERGENCY bug task
     elif count >= THRESHOLD_OCC
          or distinct_sessions >= THRESHOLD_SESS: → create ICEBOX bug task
     else: leave 'open' (not yet worth a card)
   On create: cos_task_search(label="fp:<fingerprint>") FIRST (belt-and-suspenders vs the task_id link);
              body = scope + exc_type + sample_msg + stack + first/last/count + a cos_log_query recipe;
              set log_fingerprints.task_id, status='filed'.
3. Reconcile: status=='filed' && last_seen older than COS_ERROR_RECONCILE_DAYS
              → move task to archive, status='archived'  (recurrence reopens it).
4. Retention prune (after rollup): delete aged log_events rows per level.
```

**Anti-recursion:** the sweep logs under reserved scope `ops.error_sweep`, which is **excluded** from fingerprint input. If the sweep itself errors, that error is captured by the eye but never files a task about itself. **Anti-spam:** one fingerprint = one task forever (idempotent); `--dry-run` prints planned creates without writing.

## 5. Failure modes & invariants

| # | Invariant | Why |
|---|---|---|
| I1 | A sink failure must NOT re-enter `logging_os` — write to stderr-of-last-resort + `dropped_events++` only. | Prevents infinite log→sink-error→log loops. The eye reports its own blindness instead of hanging. |
| I2 | `DEBUG`/`INFO` NEVER touch the DB (WARN+ gate). | Logging must not slow the 95% hot path. Async machinery is deferred v2 speculation until WARN+ volume is *measured* hot (Rule 22). |
| I3 | Security/enforcement hooks default **DENY** on helper crash, capturing the crash. | A guard that can't evaluate must not silently allow (the `branch-guard` fail-open class). |
| I4 | Redaction runs before ANY durable sink (DB *and* jsonl). | A secret in a durable store is permanent. Scrub Bearer/JWT/`key=` shapes + a kv-key denylist. |
| I5 | One fingerprint = one task forever; re-running the sweep creates no duplicates. | Board-spam protection; idempotency via `log_fingerprints.task_id`. |
| I6 | `fatal()` raises `CosFatalError`; only the CLI entrypoint may `sys.exit`. | An in-library `sys.exit(1)` from a server/MCP context would kill the uvicorn/FastMCP worker. |
| I7 | Sink path/format resolves from `logging_os.config` everywhere (no hardcoded `.coding-os`). | On `COS_STATE_DIR` override the writer and the UI must tail the same file (Rule 1/4, api-contract-discipline). |
| I8 | An irreversible/integrity-harm gate that cannot extract its decision input (no jq **and** no python3) defaults **DENY**. Extraction degrades jq→python3 first (`cos_json_field`); only the no-parser floor blocks (`cos_require_parser`). | Extends I3 from the helper-crash class to the jq-extraction class. The old `jq … \|\| echo ""` returned empty → `exit 0` → the secret/data-loss gate silently disabled itself when jq was absent. python3 is a hard dep, so the realistic degraded case keeps the gate *functioning*; the no-parser case is the only one that blocks. Bootstrap escape: `COS_ALLOW_MISSING_DEPS=1`. |
| I9 | The hook layer is self-measuring: every `cos_log_hook` line carries `dt=<ms>` (wall-time since hook entry), and PreToolUse Bash fan-out width is capped by a regression test (`tests/test_hook_fanout_budget.py`). | You cannot manage overhead you do not measure. Second-resolution timestamps made per-hook latency underivable; unbounded fan-out is the death-by-a-thousand-hooks creep. |

## 6. Config keys

Routed through `scheduled/config.py` DEFAULTS + `_INT_BOUNDS` (zero new route code) and `logging_os/config.py` env reads:

| Key | Default | Meaning |
|---|---|---|
| `COS_LOG_LEVEL` | `info` | producer level floor (existing) |
| `COS_LOG_MAX_LINES` | `5000` | jsonl tail cap (existing, hot path only) |
| `COS_LOG_DB_MIN_LEVEL` | `WARN` | durability gate — events ≥ this persist to `log_events` |
| `COS_LOG_RETENTION_ERROR_DAYS` | `30` | raw-row retention for ERROR/FATAL |
| `COS_LOG_RETENTION_WARN_DAYS` | `7` | raw-row retention for WARN |
| `COS_ERROR_SWEEP_ENABLED` | `true` | master switch for the error→bug sweep |
| `COS_ERROR_THRESHOLD_OCC` | `3` | ERROR occurrences before a card |
| `COS_ERROR_THRESHOLD_SESSIONS` | `2` | distinct sessions before a card |
| `COS_ERROR_RECONCILE_DAYS` | `7` | no-recurrence window → archive the card |

## 7. Roadmap — the `observability-eye` epic

Trunk-based, one commit per task, MVP→v1→v2. Each task anchors to the section above.

**Status (2026-06-05):** E0 (this doc) + E1–E10 + E12 **shipped** — 11 commits, the full backend eye (capture → durable store → query MCP+CLI → security → enrichment → drift → doctor → envelope → auto-bug-sweep), each verified. **E11** (Hub Errors view) deferred → TASK-147 (heavier React + ui-build slice; the existing LogsPage already tails the jsonl). **E13** (exhaustive silent-handler conversion + `swallow_safe()`) deferred → TASK-148 (must coordinate with the active TASK-100 output-quality work, not run concurrently). Minor refinements deferred: `cos_say` scope-width (E10), sweep retention/reconcile + FATAL→emergency-status escalation (E12).

| Task | Phase | Anchor | Outcome |
|---|---|---|---|
| E1 bridge install (web + cli + mcp) | MVP | §1 | every CLI/web/MCP stdlib error reaches the eye |
| E2 migration v32 `log_events` + `log_fingerprints` | MVP | §2 | durable, indexed cold store |
| E3 WARN+ DB sink + fallback + `dropped_events` | MVP | §1, I1 | WARN+ persists; sink blindness is itself observable |
| E4 `cos_log_query` MCP | MVP | §3 | agent can ask "what errored since X" |
| E5 `cos logs` / `cos errors` CLI | MVP | §3 | human + CLI-agent durable error access |
| E6 fail-CLOSED security fix (branch-guard + detect-exhaustive-intent) | MVP | I3 | guards stop failing open; crashes captured |
| E7 `cos doctor` runtime.recent_errors check | v1 | §3 | doctor sees live breakage; CI exit reflects it |
| E8 `@safe_tool` on `cos_task_show` / `cos_task_move` | v1 | §1 | no raw MCP protocol throws |
| E9 traceback + trace_id + redaction + `fatal()` fix + `error(exc=)` | v1 | §1, I4, I6 | durable errors are actionable + secret-free + worker-safe |
| E10 path/format drift fixes (logs.py SSOT, TZ bug, runtime_paths, cos_say width) | v1 | I7 | one path, one format, correct since-filter |
| E11 Hub Errors view + `/api/logs/summary` + error-aware alarm bar | v2 | §3 | "what is broken now" at a glance |
| E12 nightly error→bug-task sweep (fingerprint dedup + retention) | v2 | §4 | recurring errors become pullable bug cards |
| E13 exhaustive silent-handler conversion + `swallow_safe()` + `cos_say` adoption | v2 | §1 | ~95% adoption; coord TASK-100; audit-tracked |
| E14 hook hardening: fail-closed parser invariant across all gates + `dt=` latency SLI + fan-out budget + decision-state hooks-log | v1 | I8, I9 | TASK-196 — extends E6 from 2 gates to the full block-\*/enforce-\* set; the hook bus measures + bounds itself |

## See also

- [logging_os.md](logging_os.md) — the producer facade contract (event schema, renders, sinks).
- [mcp-error-envelope.md](mcp-error-envelope.md) — the `ok`/`fail` contract `cos_log_query` follows.
- [../../src/core/rules/api-contract-discipline.md](../../src/core/rules/api-contract-discipline.md) — field-name SSOT (route emit ↔ UI read).
- [state-files.md](state-files.md) — `COS_STATE_DIR`/`COS_PANEL_DIR` resolution the sink honors.
- `docs/tasks/TASK-101-*` — the epic anchor task; E1–E13 are its children.
