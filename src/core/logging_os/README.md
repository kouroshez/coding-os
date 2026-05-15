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
fatal("cli.main", "uv not on PATH — abort")     # also sys.exit(1)
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

Sinks fail-open. Log errors never propagate to the caller.

## Files

```
__init__.py     # public API re-export
api.py          # 6 producer functions + scoped()
render.py       # 3 pure renderers + EMOJI / COLOR maps
sinks.py        # fan-out writer
config.py       # Level enum, env vars, detect_render(), setup()
tests/          # pytest suite
```
