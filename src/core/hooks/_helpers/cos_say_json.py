"""Shell→logging_os helper: render the jsonl line AND persist the durable row.

cos-env.sh's cos_say calls this for every above-floor event (its jsonl render);
cos_log_hook calls it on a BLOCK. Beyond printing the flat json line (consumed
by the shell for ${COS_LOG_FILE}.jsonl), it inserts the event into the SQLite
log_events store the logging_os sink owns (F8/TASK-447) so cos_log_query and
error_sweep surface a hook BLOCK/WARN — not just the text/jsonl tail. This is
the single shell→DB writer both shell paths share.

DB-only side effect: stderr + text + jsonl are written by the shell caller.
Fail-open everywhere — logging must never abort a hook.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

RESERVED_KEYS = ("ts", "lvl", "scope", "msg")

# Mirrors logging_os.config.Level — duplicated only to pre-gate the durable
# write WITHOUT importing logging_os on the hot sub-threshold path (a cos_say
# at info/ok fires this helper but must stay fast). The authoritative gate
# still runs inside _write_db; this just avoids the import when it would no-op.
_LEVEL_VALUE = {"DEBUG": 10, "INFO": 20, "OK": 21, "WARN": 30, "ERROR": 40, "FATAL": 50}


def _persist_db_row(ts: str, level: str, scope: str, message: str, kv: dict[str, str]) -> None:
    floor = _LEVEL_VALUE.get(os.environ.get("COS_LOG_DB_MIN_LEVEL", "WARN").upper(), 30)
    if _LEVEL_VALUE.get(level.upper(), 20) < floor:
        return  # sub-threshold: never import logging_os, never touch the store
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from logging_os.sinks import _write_db

        _write_db(
            {
                "ts": ts,
                "lvl": level.upper(),
                "scope": scope,
                "msg": message,
                "kv": kv,
                "session_id": kv.get("session"),
                "trace_id": kv.get("trace") or kv.get("trace_id"),
            }
        )
    except Exception as exc:  # fail-open — a logging failure must never break the hook
        _note_durable_failure(level, scope, exc)


def _note_durable_failure(level: str, scope: str, exc: Exception) -> None:
    # The bare swallow used to make a logging_os import break (the documented
    # "logging_os RED on main" class) a SILENT no-op — every WARN+/BLOCK absent
    # from cos_log_query with zero signal, because the drop-observability lives
    # inside _write_db which an import failure never reaches. Leave a breadcrumb
    # that survives the caller's `2>/dev/null` (the durable text log first, then
    # stderr) so the dropped durable write is at least discoverable. Still
    # fail-open: never raise. (audit pass-4 #1)
    note = (
        f"logging_os: durable sink unavailable ({type(exc).__name__}: {exc}) "
        f"— {level.upper()} {scope} not persisted to log_events\n"
    )
    log_file = os.environ.get("COS_LOG_FILE")
    if log_file:
        try:
            with open(log_file, "a", encoding="utf-8") as handle:
                handle.write(note)
            return
        except OSError:
            note += "  (text log also unwritable)\n"  # fall through to stderr
    try:
        sys.stderr.write(note)
    except OSError:
        return  # last-resort sink failed too — nothing left to do, stay fail-open


def main() -> int:
    if len(sys.argv) < 6:
        return 1
    ts, level, scope, message, kv_blob = sys.argv[1:6]
    kv: dict[str, str] = {}
    if kv_blob:
        for token in shlex.split(kv_blob):
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            kv[key] = value
    event = {"ts": ts, "lvl": level, "scope": scope, "msg": message}
    for key, value in kv.items():
        if key in RESERVED_KEYS or key in event:
            continue
        event[key] = value
    sys.stdout.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    _persist_db_row(ts, level, scope, message, kv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
