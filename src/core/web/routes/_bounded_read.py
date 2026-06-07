"""Bounded file/dir reads for the observability + cognition routes.

A log or trace can grow to many GB; the Hub must never load one whole into
memory (it would OOM the server). These helpers read only a fixed tail window
and scan only the newest-N files by mtime, so latency + memory stay flat as
the on-disk corpus grows. TASK-225.
"""

from __future__ import annotations

import os
from pathlib import Path

# Default tail window — mirrors presence.py::_latest_transcript_usage.
DEFAULT_WINDOW = 256 * 1024  # 256 KB


def tail_text(path: Path, max_bytes: int = DEFAULT_WINDOW) -> str:
    """Return up to the last `max_bytes` of a file as utf-8 text (errors
    ignored). Seeks to the tail — safe on multi-GB files."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            window = min(size, max_bytes)
            fh.seek(-window, os.SEEK_END)
            return fh.read().decode("utf-8", errors="ignore")
    except OSError:
        return ""


def tail_lines(
    path: Path,
    max_lines: int | None = None,
    max_bytes: int = DEFAULT_WINDOW,
) -> tuple[list[str], bool]:
    """Return (lines, truncated) from the tail of a file.

    Reads only the last `max_bytes`; when the file is larger, the first
    (partial) line in the window is dropped and `truncated` is True. When
    `max_lines` is set, only the last that many complete lines are returned.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return [], False
    text = tail_text(path, max_bytes)
    if not text:
        return [], size > 0
    lines = text.splitlines()
    truncated = size > max_bytes
    if truncated and len(lines) > 1:
        lines = lines[1:]  # window started mid-line — drop the partial head
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[-max_lines:]
        truncated = True
    return lines, truncated


def newest_files(directory: Path, pattern: str, limit: int) -> list[Path]:
    """Up to `limit` files matching `pattern`, newest-first by mtime. Bounds a
    directory scan that would otherwise glob an unbounded set. `limit<=0`
    returns all matches (unbounded — caller opts in explicitly)."""
    try:
        files = list(directory.glob(pattern))
    except OSError:
        return []
    files.sort(key=_safe_mtime, reverse=True)
    return files[:limit] if limit and limit > 0 else files


def _safe_mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0
