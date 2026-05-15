from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .config import detect_render, jsonl_log_path, max_log_lines, text_log_path
from .render import render


def _write_stderr(event: dict[str, Any]) -> None:
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
    _append_line(text_log_path(), render("short", event))


def _write_jsonl_file(event: dict[str, Any]) -> None:
    _append_line(jsonl_log_path(), render("json", event))


def dispatch(event: dict[str, Any]) -> None:
    _write_stderr(event)
    _write_text_file(event)
    _write_jsonl_file(event)
