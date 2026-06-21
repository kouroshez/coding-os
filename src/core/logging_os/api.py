from __future__ import annotations

import traceback
from datetime import datetime, timezone
from typing import Any

from .config import Level, current_level, db_min_level, normalize_scope, session_id, trace_id
from .redact import redact_kv, redact_text
from .sinks import dispatch


# Raised by fatal() after emitting — the caller (CLI) decides whether to exit.
# Never kills a server/MCP worker the way an in-library sys.exit(1) would.
class CosFatalError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _emit(
    level: Level, scope: str, msg: str, kv: dict[str, Any], exc: BaseException | None = None
) -> None:
    # Per-sink flooring (TASK-473): short-circuit only when the level clears
    # NEITHER floor. The console floor (COS_LOG_LEVEL) gates stderr/text/jsonl in
    # dispatch(); the independent durability floor (COS_LOG_DB_MIN_LEVEL) gates the
    # DB sink. Flooring at the console level alone here dropped a WARN before the
    # durable store (db_min_level=WARN) ever saw it.
    if level < min(current_level(), db_min_level()):
        return
    canonical, raw_invalid = normalize_scope(scope)
    extras = redact_kv(dict(kv))
    if raw_invalid is not None and raw_invalid != "":
        extras.setdefault("raw_scope", raw_invalid)
    # `stack` is a first-class durable column, not a kv field — lift it out.
    stack = extras.pop("stack", None)
    if exc is not None:
        extras.setdefault("exc", type(exc).__name__)
        if stack is None:
            stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    event: dict[str, Any] = {
        "ts": _now_iso(),
        "lvl": level.label,
        "scope": canonical,
        "msg": redact_text(msg),
        "kv": extras,
    }
    if stack:
        event["stack"] = redact_text(stack)[-2000:]
    sid = session_id()
    if sid:
        event["session_id"] = sid
    tid = trace_id()
    if tid:
        event["trace_id"] = tid
    dispatch(event)


def debug(scope: str, msg: str, **kv: Any) -> None:
    _emit(Level.DEBUG, scope, msg, kv)


def info(scope: str, msg: str, **kv: Any) -> None:
    _emit(Level.INFO, scope, msg, kv)


def ok(scope: str, msg: str, **kv: Any) -> None:
    _emit(Level.OK, scope, msg, kv)


def warn(scope: str, msg: str, **kv: Any) -> None:
    _emit(Level.WARN, scope, msg, kv)


def error(scope: str, msg: str, exc: BaseException | None = None, **kv: Any) -> None:
    _emit(Level.ERROR, scope, msg, kv, exc=exc)


def fatal(scope: str, msg: str, exc: BaseException | None = None, **kv: Any) -> None:
    _emit(Level.FATAL, scope, msg, kv, exc=exc)
    raise CosFatalError(msg)


_swallowed_count = 0


def swallow_safe(
    scope: str, msg: str = "suppressed exception", *, exc: BaseException | None = None
) -> None:
    """For fire-and-forget paths: acknowledge a swallowed exception (debug log + counter) — never silent."""
    global _swallowed_count
    _swallowed_count += 1
    _emit(Level.DEBUG, scope, msg, {}, exc=exc)


def swallowed_count() -> int:
    return _swallowed_count


class ScopedLogger:
    __slots__ = ("scope",)

    def __init__(self, scope: str) -> None:
        self.scope = scope

    def debug(self, msg: str, **kv: Any) -> None:
        debug(self.scope, msg, **kv)

    def info(self, msg: str, **kv: Any) -> None:
        info(self.scope, msg, **kv)

    def ok(self, msg: str, **kv: Any) -> None:
        ok(self.scope, msg, **kv)

    def warn(self, msg: str, **kv: Any) -> None:
        warn(self.scope, msg, **kv)

    def error(self, msg: str, exc: BaseException | None = None, **kv: Any) -> None:
        error(self.scope, msg, exc=exc, **kv)

    def fatal(self, msg: str, exc: BaseException | None = None, **kv: Any) -> None:
        fatal(self.scope, msg, exc=exc, **kv)


def scoped(scope: str) -> ScopedLogger:
    return ScopedLogger(scope)
