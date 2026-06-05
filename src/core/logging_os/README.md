# logging_os

Central log helpers — one producer API, three renders, three sinks. Stdlib only.

Full contract: [docs/engineering/logging_os.md](../../../docs/engineering/logging_os.md).

## Quick reference

```python
from core.logging_os import setup, ok, info, warn, error, fatal, debug, scoped

setup(level="info")

info("cli.doctor", "starting check sweep")
ok("cli.doctor", "all 38 checks green", count=38)
warn("hook.enforce_skill", "graph-explorer not loaded", file="src/core/x.py")
error("thinking_os.server", "db migration v23 failed", code="DUPCOL")
fatal("cli.main", "uv not on PATH — abort")     # emits then raises CosFatalError
error("thinking_os.server", "capture failed", exc=e)  # error/fatal take exc= → stack captured
debug("graph_os.indexer", "upserted nodes", count=14)

doctor = scoped("cli.doctor")
doctor.warn("disk almost full", free_mb=120)
```

Shell parity (`cos_say` in `src/core/hooks/cos-env.sh`):

```bash
cos_say warn hook.enforce_skill "graph-explorer not loaded" file=src/core/x.py
```

## Render auto-detection

| Trigger | Render |
|---|---|
| `COS_LOG_JSON=1` | `json` |
| `COS_LOG_FORCE_PRETTY=1` | `pretty` |
| `NO_COLOR` set | `short` |
| `sys.stderr.isatty()` true | `pretty` |
| otherwise | `short` |

## Sinks (every event fans out)

| Sink | Render | Path |
|---|---|---|
| stderr | per-detect | — |
| text file | `short` | `$COS_LOG_FILE` (default `$COS_STATE_DIR/.cos.log`) |
| jsonl file | `json` | `$COS_LOG_FILE.jsonl` |
| sqlite (WARN+) | — | `log_events` in `$COS_DB_PATH` — durable, queryable system-of-record |

Sinks fail-open. Log errors never propagate to the caller. The sqlite sink is
gated to `$COS_LOG_DB_MIN_LEVEL` (default `WARN`) so the debug/info hot path
never touches the DB; it no-ops when no DB exists and counts write failures in
`sinks.dropped_events()`. Durable store + query contract:
[observability-eye.md](../../../docs/engineering/observability-eye.md).

## Files

```
__init__.py     # public API re-export
api.py          # 6 producer functions + scoped()
render.py       # 3 pure renderers + EMOJI / COLOR maps
sinks.py        # fan-out writer (stderr + text + jsonl + WARN+ sqlite)
fingerprint.py  # stable error fingerprint (scope + exc + normalized msg)
redact.py       # secret-shape + sensitive-key redaction (runs before every sink)
config.py       # Level enum, env vars, detect_render(), setup(), db_path(), session_id()
tests/          # pytest suite
```
