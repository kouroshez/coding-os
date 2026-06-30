from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from .config import (
    Level,
    current_level,
    db_min_level,
    db_path,
    detect_render,
    jsonl_log_path,
    max_log_lines,
    text_log_path,
)
from .fingerprint import fingerprint
from .render import render

_dropped_events = 0


def _event_level(event: dict[str, Any]) -> Level | None:
    try:
        return Level.from_name(event.get("lvl", ""))
    except ValueError:
        return None


def _below_console_floor(event: dict[str, Any]) -> bool:
    """True when this event is under the console floor (COS_LOG_LEVEL) — the
    gate for the human-facing sinks (stderr + text mirror + jsonl tail). An
    unparseable level fails OPEN (printed) rather than silently dropped."""
    level = _event_level(event)
    return level is not None and level < current_level()


def _write_stderr(event: dict[str, Any]) -> None:
    if _below_console_floor(event):
        return
    line = render(detect_render(), event)
    try:
        sys.stderr.write(line + "\n")
        sys.stderr.flush()
    except (BrokenPipeError, OSError, ValueError):
        return


def _truncate_if_needed(path: Path, cap: int) -> None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
        if len(lines) <= cap * 2:
            return
        keep = lines[-cap:]
        with path.open("w", encoding="utf-8") as handle:
            handle.writelines(keep)
    except OSError:
        return


def _append_line(path: Path, line: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        return
    _truncate_if_needed(path, max_log_lines())


def _write_text_file(event: dict[str, Any]) -> None:
    if _below_console_floor(event):
        return
    _append_line(text_log_path(), render("short", event))


def _write_jsonl_file(event: dict[str, Any]) -> None:
    if _below_console_floor(event):
        return
    _append_line(jsonl_log_path(), render("json", event))


def _record_dropped() -> None:
    global _dropped_events
    _dropped_events += 1
    # Last-resort notice to raw stderr. MUST NOT route through logging_os — a
    # sink failure re-entering the producer would recurse (invariant I1).
    try:
        sys.stderr.write(f"logging_os: dropped 1 durable log event (total={_dropped_events})\n")
    except Exception:
        return


def dropped_events() -> int:
    return _dropped_events


def _insert_log_event(path: Path, event: dict[str, Any]) -> None:
    kv = event.get("kv") or {}
    exc_type = kv.get("exc")
    base = (
        event["ts"],
        event["lvl"],
        event["scope"],
        event["msg"],
        json.dumps(kv, ensure_ascii=False) if kv else None,
        exc_type,
        event.get("stack"),
        event.get("session_id"),
        event.get("trace_id"),
        fingerprint(event["scope"], exc_type, event["msg"]),
    )
    cols = "ts, lvl, scope, msg, kv, exc_type, stack, session_id, trace_id, fingerprint"
    conn = sqlite3.connect(str(path), timeout=2.0)
    try:
        conn.execute("PRAGMA busy_timeout=2000")
        try:
            conn.execute(
                f"INSERT INTO log_events ({cols}, event_class) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*base, event.get("event_class", "fault")),
            )
        except sqlite3.OperationalError:
            # pre-v46 DB without event_class — never drop an event over a column
            conn.execute(
                f"INSERT INTO log_events ({cols}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                base,
            )
        conn.commit()
    finally:
        conn.close()


def _write_db(event: dict[str, Any]) -> None:
    level = _event_level(event)
    if level is None or level < db_min_level():
        return  # hot path: debug/info/ok never touch the durable store
    path = db_path()
    if not path.exists():
        return  # no durable store here — the jsonl tail still has the event
    try:
        _insert_log_event(path, event)
    except Exception:
        _record_dropped()  # fail-open + observable (I1) — never raise to the caller


def dispatch(event: dict[str, Any]) -> None:
    _write_stderr(event)
    _write_text_file(event)
    _write_jsonl_file(event)
    _write_db(event)
