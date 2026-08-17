"""Envelope, marker, validation, and telemetry primitives for cos_graph_*.

Leaf of graph_os.tools.graph — imports no sibling tool module.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from ..backend import GraphBackend

logger = logging.getLogger("graph_os.tools.graph")


# ---------------------------------------------------------------------------
# Envelope helpers — shared with thinking_os via sys.path.
# ---------------------------------------------------------------------------


def _envelope_module():
    try:
        from tools import _shared  # type: ignore

        return _shared
    except ImportError:
        here = Path(__file__).resolve()
        candidate = here.parent.parent.parent / "thinking_os"
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
        from tools import _shared  # type: ignore

        return _shared


def _ok(data: dict[str, Any], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    shared = _envelope_module()
    merged = {"layer": "graph", **(meta or {})}
    _emit_telemetry(meta=merged, ok=True)
    _touch_session_marker()
    return shared.ok(data, meta=merged)


def _touch_session_marker() -> None:
    """Record that a cos_graph_* call succeeded this agent session.

    Consumed by enforce-graph-first-read.sh — when the marker exists,
    the hook stays silent on Read. Fail-open: any error is logged at
    debug level only, never raises.
    """
    try:
        agent_dir = os.environ.get("COS_AGENT_DIR")
        if not agent_dir:
            state_dir = os.environ.get("COS_STATE_DIR") or ".coding-os"
            agent = os.environ.get("COS_AGENT") or "claude"
            agent_dir = f"{state_dir}/{agent}"
        from pathlib import Path as _Path

        path = _Path(agent_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / ".graph-call-seen").touch(exist_ok=True)
    except OSError as exc:
        logger.debug("graph-call-seen marker failed: %s", exc)


def _file_disk_hash(file_path: str) -> str | None:
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _graph_marker_dir() -> Path:
    # Agent-scoped, not panel-scoped: the shared MCP server resolves
    # COS_AGENT_DIR but never the calling tab's panel. The content_hash
    # binding below is what makes the wider scope safe — a marker counts
    # only while the consulted content still matches disk, whoever read it.
    agent_dir = os.environ.get("COS_AGENT_DIR")
    if not agent_dir:
        state_dir = os.environ.get("COS_STATE_DIR") or ".coding-os"
        agent = os.environ.get("COS_AGENT") or "claude"
        agent_dir = f"{state_dir}/{agent}"
    return Path(agent_dir) / ".graph"


def _write_consult_marker(name: str, payload: dict[str, Any]) -> None:
    try:
        marker_dir = _graph_marker_dir()
        marker_dir.mkdir(parents=True, exist_ok=True)
        (marker_dir / name).write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        logger.debug("graph consult marker failed: %s", exc)


def _file_freshness(backend_obj: GraphBackend, file_path: str | None) -> dict[str, Any] | None:
    if not file_path:
        return None
    disk = _file_disk_hash(file_path)
    file_node = backend_obj.get_node(f"code:file:{file_path}")
    indexed = file_node.content_hash if file_node else None
    if disk is None or indexed is None:
        return None
    return {"stale": disk != indexed, "disk_hash": disk, "indexed_hash": indexed}


def _fail(
    category: str,
    message: str,
    *,
    retryable: bool | None = None,
) -> dict[str, Any]:
    shared = _envelope_module()
    _emit_telemetry(
        meta={"layer": "graph", "category": category, "message": message},
        ok=False,
    )
    return shared.fail(category, message, retryable=retryable)


def _validate_positive_int(value: Any, field: str) -> Any:
    if not isinstance(value, int) or value <= 0:
        return _fail("validation", f"{field} must be a positive int (got {value!r})")
    return None


def _validate_non_negative_int(value: Any, field: str) -> Any:
    if not isinstance(value, int) or value < 0:
        return _fail("validation", f"{field} must be >= 0 (got {value!r})")
    return None


def _validate_enum(value: Any, allowed: tuple[str, ...], field: str) -> Any:
    if value not in allowed:
        return _fail("validation", f"{field} must be one of {allowed} (got {value!r})")
    return None


def _clamp_int(value: int, *, min_v: int, max_v: int) -> tuple[int, bool]:
    clamped = max(min_v, min(int(value), max_v))
    return clamped, clamped != value


def _validate_confidence(value: Any, field: str) -> Any:
    # W7.1 / R4-19/R4-26: confidence is in [0.0, 1.0]; impact + query
    # silently accepted 999 and filtered everything.
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return _fail("validation", f"{field} must be a number (got {type(value).__name__})")
    if value < 0.0 or value > 1.0:
        return _fail("validation", f"{field} must be in [0.0, 1.0] (got {value})")
    return None


def _validate_min_chars(value: Any, field: str, *, min_chars: int = 2) -> Any:
    # W7.1 / R4-09: cos_graph_query enforces 2-char min; cos_graph_resolve
    # silently accepted single-char fuzzy. Parity.
    if not isinstance(value, str):
        return _fail("validation", f"{field} must be a string (got {type(value).__name__})")
    if len(value.strip()) < min_chars:
        return _fail("validation", f"{field} must be at least {min_chars} chars")
    return None


# -- Telemetry --------------------------------------------------------
# Append-only JSONL log of every cos_graph_* invocation. One line per
# call: {ts, ok, layer, source, backend, ...meta}. The file lives in
# $COS_STATE_DIR/.graph-telemetry.jsonl and is rotated when it crosses
# a soft cap so the disk footprint stays bounded.

_TELEMETRY_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
_TELEMETRY_PATH_CACHE: list[str] = []


def _project_state_dir() -> str | None:
    # The previous fallback was `Path.cwd() / ".coding-os"` + mkdir, which minted
    # a state dir wherever the process happened to be. A minted dir is itself a
    # root marker, so it then captured every later resolution in that subtree —
    # src/core/web/ui/ ran on its own phantom DB for two months. Walk instead,
    # and degrade to None rather than invent a root (state-files.md).
    state_dir = os.environ.get("COS_STATE_DIR")
    if state_dir:
        return state_dir
    try:
        from thinking_os._db_paths import _find_project_root_from_cwd
    except ImportError as exc:
        logger.debug("telemetry root walk unavailable: %s", exc)
        return None
    root = _find_project_root_from_cwd()
    return str(root / ".coding-os") if root is not None else None


def _telemetry_path() -> str | None:
    if _TELEMETRY_PATH_CACHE:
        return _TELEMETRY_PATH_CACHE[0]
    state_dir = _project_state_dir()
    if not state_dir:
        return None
    try:
        from pathlib import Path as _Path

        path = _Path(state_dir)
        # exist_ok + no parents: the walk already proved this root exists, so
        # this creates at most the state dir itself, never a tree at cwd.
        path.mkdir(exist_ok=True)
        full = str(path / ".graph-telemetry.jsonl")
        _TELEMETRY_PATH_CACHE.append(full)
        return full
    except OSError as exc:
        logger.debug("telemetry path setup failed: %s", exc)
        return None


def _rotate_telemetry_atomically(path: str) -> None:
    try:
        size = os.path.getsize(path)
    except OSError:
        return
    if size <= _TELEMETRY_MAX_BYTES:
        return
    tmp = f"{path}.rotating"
    try:
        with open(path, "rb") as src:
            src.seek(size // 2)
            tail = src.read()
        with open(tmp, "wb") as dst:
            dst.write(tail)
        os.replace(tmp, path)
    except OSError as exc:
        logger.debug("telemetry rotation skipped: %s", exc)
        with contextlib.suppress(OSError):
            os.unlink(tmp)


def _emit_telemetry(*, meta: dict[str, Any], ok: bool) -> None:
    """Append one JSONL row. Fail-open — telemetry must never block a tool."""
    try:
        path = _telemetry_path()
        if path is None:
            return
        import json as _json
        import time as _time

        row = {
            "ts": int(_time.time()),
            "ok": ok,
            **{k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool))},
        }
        line = _json.dumps(row, default=str) + "\n"
        _rotate_telemetry_atomically(path)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception as exc:
        logger.debug("telemetry emit suppressed: %s", exc)
