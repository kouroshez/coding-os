from __future__ import annotations

import os
import re
import sys
from enum import IntEnum
from pathlib import Path

DEFAULT_SCOPE_WIDTH = 20
SCOPE_PATTERN = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
SCOPE_MAX_LENGTH = 40
INVALID_SCOPE_FALLBACK = "invalid.scope"


class Level(IntEnum):
    DEBUG = 10
    INFO = 20
    OK = 21
    WARN = 30
    ERROR = 40
    FATAL = 50

    @classmethod
    def from_name(cls, name: str) -> Level:
        upper = name.upper()
        if upper not in cls.__members__:
            raise ValueError(f"unknown log level: {name}")
        return cls[upper]

    @property
    def label(self) -> str:
        return self.name


STATE_DIR_NAME = ".coding-os"
LOG_BASENAME = ".cos.log"


def _discover_project_root() -> Path | None:
    # Walk up from the process CWD for a project marker so the .coding-os state
    # dir anchors to the PROJECT ROOT, not wherever the process happened to start.
    # Returns None when no marker is found (caller keeps the CWD fallback).
    # Marker set + $HOME hard-stop mirror
    # thinking_os.database._find_project_root_from_cwd (kept aligned by hand so
    # logging_os stays dependency-free of thinking_os).
    markers = (".git", ".coding-os.yaml", "pyproject.toml", "package.json", "go.mod", "AGENTS.md")
    try:
        here = Path.cwd().resolve()
        home = Path.home().resolve()
    except (OSError, RuntimeError):
        return None
    for parent in (here, *here.parents):
        if parent == home:  # never anchor at $HOME (the global hub lives there)
            break
        if any((parent / m).exists() for m in markers):
            return parent
    return None


def state_dir() -> Path:
    explicit = os.environ.get("COS_STATE_DIR")
    if explicit:
        return Path(explicit)
    # Anchor .coding-os to the project root, not the process CWD. Without this a
    # process started from a subdir (e.g. the MCP server under src/core/thinking_os)
    # wrote its logs/DB to a sibling .coding-os/ the Hub (rooted at the repo) never
    # reads, fragmenting the log feed across CWDs. COS_STATE_DIR still
    # wins; no project marker falls back to the legacy CWD-relative path.
    root = _discover_project_root()
    return (root / STATE_DIR_NAME) if root else Path(STATE_DIR_NAME)


def text_log_path(root: Path | None = None) -> Path:
    # An explicit project root is authoritative — the multi-project Hub resolves
    # a specific project's sink and must not be overridden by the ambient
    # COS_LOG_FILE (the launch project's). root=None keeps the env/cwd default.
    if root is not None:
        return root / STATE_DIR_NAME / LOG_BASENAME
    explicit = os.environ.get("COS_LOG_FILE")
    if explicit:
        return Path(explicit)
    return state_dir() / LOG_BASENAME


def jsonl_log_path(root: Path | None = None) -> Path:
    base = text_log_path(root)
    return base.with_name(base.name + ".jsonl")


def current_level() -> Level:
    raw = os.environ.get("COS_LOG_LEVEL", "info")
    try:
        return Level.from_name(raw)
    except ValueError:
        return Level.INFO


def db_path() -> Path:
    explicit = os.environ.get("COS_DB_PATH")
    if explicit:
        return Path(explicit)
    return state_dir() / "coding-os.db"


def db_min_level() -> Level:
    raw = os.environ.get("COS_LOG_DB_MIN_LEVEL", "WARN")
    try:
        return Level.from_name(raw)
    except ValueError:
        return Level.WARN


def session_id() -> str:
    return os.environ.get("COS_SESSION_ID") or os.environ.get("COS_PANEL_ID", "")


def trace_id() -> str:
    return os.environ.get("COS_TRACE_ID", "")


def detect_render() -> str:
    if os.environ.get("COS_LOG_JSON") == "1":
        return "json"
    if os.environ.get("COS_LOG_FORCE_PRETTY") == "1":
        return "pretty"
    if os.environ.get("NO_COLOR"):
        return "short"
    if not sys.stderr.isatty():
        return "short"
    return "pretty"


def max_log_lines() -> int:
    raw = os.environ.get("COS_LOG_MAX_LINES", "5000")
    try:
        value = int(raw)
    except ValueError:
        return 5000
    return max(100, value)


def scope_width() -> int:
    raw = os.environ.get("COS_LOG_SCOPE_WIDTH", str(DEFAULT_SCOPE_WIDTH))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_SCOPE_WIDTH
    return max(4, min(value, 60))


def normalize_scope(scope: str) -> tuple[str, str | None]:
    if not isinstance(scope, str) or not scope:
        return INVALID_SCOPE_FALLBACK, ""
    candidate = scope.strip()
    if len(candidate) > SCOPE_MAX_LENGTH:
        return INVALID_SCOPE_FALLBACK, candidate
    if not SCOPE_PATTERN.match(candidate):
        return INVALID_SCOPE_FALLBACK, candidate
    return candidate, None


def setup(level: str | Level = "info", install_stdlib_bridge: bool = True) -> None:
    if isinstance(level, Level):
        resolved = level
        os.environ["COS_LOG_LEVEL"] = level.name.lower()
    else:
        resolved = Level.from_name(level)
        os.environ["COS_LOG_LEVEL"] = level.lower()
    if install_stdlib_bridge:
        from .bridge import install_bridge

        install_bridge(resolved)
