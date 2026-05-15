from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any

from .config import Level, current_level, normalize_scope
from .sinks import dispatch


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _emit(level: Level, scope: str, msg: str, kv: dict[str, Any]) -> None:
    if level < current_level():
        return
    canonical, raw_invalid = normalize_scope(scope)
    extras = dict(kv)
    if raw_invalid is not None and raw_invalid != "":
        extras.setdefault("raw_scope", raw_invalid)
    event = {
        "ts": _now_iso(),
        "lvl": level.label,
        "scope": canonical,
        "msg": msg,
        "kv": extras,
    }
    dispatch(event)


def debug(scope: str, msg: str, **kv: Any) -> None:
    _emit(Level.DEBUG, scope, msg, kv)


def info(scope: str, msg: str, **kv: Any) -> None:
    _emit(Level.INFO, scope, msg, kv)


def ok(scope: str, msg: str, **kv: Any) -> None:
    _emit(Level.OK, scope, msg, kv)


def warn(scope: str, msg: str, **kv: Any) -> None:
    _emit(Level.WARN, scope, msg, kv)


def error(scope: str, msg: str, **kv: Any) -> None:
    _emit(Level.ERROR, scope, msg, kv)


def fatal(scope: str, msg: str, **kv: Any) -> None:
    _emit(Level.FATAL, scope, msg, kv)
    sys.exit(1)


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

    def error(self, msg: str, **kv: Any) -> None:
        error(self.scope, msg, **kv)

    def fatal(self, msg: str, **kv: Any) -> None:
        fatal(self.scope, msg, **kv)


def scoped(scope: str) -> ScopedLogger:
    return ScopedLogger(scope)
