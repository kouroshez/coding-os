from __future__ import annotations

import logging
import re
from typing import Any

from .api import _emit
from .config import Level

_STDLIB_TO_COS: dict[int, Level] = {
    logging.DEBUG: Level.DEBUG,
    logging.INFO: Level.INFO,
    logging.WARNING: Level.WARN,
    logging.ERROR: Level.ERROR,
    logging.CRITICAL: Level.FATAL,
}

_COS_TO_STDLIB: dict[Level, int] = {
    Level.DEBUG: logging.DEBUG,
    Level.INFO: logging.INFO,
    Level.OK: logging.INFO,
    Level.WARN: logging.WARNING,
    Level.ERROR: logging.ERROR,
    Level.FATAL: logging.CRITICAL,
}

_INVALID_SCOPE_CHAR = re.compile(r"[^a-z0-9_.]+")
_BRIDGE_MARKER_ATTR = "_cos_logging_bridge"


def _scope_from_logger_name(name: str) -> str:
    cleaned = name.lower().replace("__main__", "main")
    cleaned = _INVALID_SCOPE_CHAR.sub("_", cleaned)
    cleaned = cleaned.strip("._") or "py.unknown"
    if "." not in cleaned:
        cleaned = f"py.{cleaned}"
    return cleaned


def _record_extras(record: logging.LogRecord) -> dict[str, Any]:
    extras: dict[str, Any] = {}
    if record.exc_info and record.exc_info[0] is not None:
        extras["exc"] = record.exc_info[0].__name__
    return extras


class LoggingOsHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = _STDLIB_TO_COS.get(record.levelno, Level.INFO)
            scope = _scope_from_logger_name(record.name)
            message = record.getMessage()
            extras = _record_extras(record)
            _emit(level, scope, message, extras)
        except Exception:
            self.handleError(record)


def install_bridge(level: Level) -> LoggingOsHandler:
    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, _BRIDGE_MARKER_ATTR, False):
            root.removeHandler(existing)
    handler = LoggingOsHandler()
    setattr(handler, _BRIDGE_MARKER_ATTR, True)
    stdlib_level = _COS_TO_STDLIB.get(level, logging.INFO)
    handler.setLevel(stdlib_level)
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > stdlib_level:
        root.setLevel(stdlib_level)
    return handler


def uninstall_bridge() -> None:
    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, _BRIDGE_MARKER_ATTR, False):
            root.removeHandler(existing)
