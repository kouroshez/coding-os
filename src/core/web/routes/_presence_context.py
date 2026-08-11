"""Context-window accounting — how full a session's window is, per agent.

Every source of a token count is here: the Stop-hook stamp, the Claude snapshot
transcript, and the codex rollout tail. They change when a runtime changes how
it reports usage, which has nothing to do with how the HUD payload is shaped.
Honest-null throughout: no source, no number (TASK-192). A leaf.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("coding_os.web.presence")


def _context_window(model: str | None) -> int:
    """Context-window size for a model id: 1M for `[1m]`-marked and fable ids, else 200K."""
    if model and ("[1m]" in model or "fable" in model):
        return 1_000_000
    return 200_000


_CODEX_ROLLOUT_PATHS: dict[str, Path] = {}


def _codex_rollout_path(sdk_uuid: str) -> Path | None:
    cached = _CODEX_ROLLOUT_PATHS.get(sdk_uuid)
    if cached is not None and cached.exists():
        return cached
    base = Path.home() / ".codex" / "sessions"
    if not base.is_dir():
        return None
    try:
        for path in base.glob(f"*/*/*/rollout-*{sdk_uuid}.jsonl"):
            _CODEX_ROLLOUT_PATHS[sdk_uuid] = path
            return path
    except OSError as exc:
        logger.debug("codex rollout glob failed for %s: %s", sdk_uuid, exc)
    return None


def _codex_rollout_context(sdk_uuid: str | None) -> tuple[int, int] | None:
    """Tail a codex rollout for (used_tokens, context_window) from its last token_count event.

    Codex has no Stop hook surface to stamp used_tokens, so the read side tails
    the rollout the codex CLI itself writes. Honest-None on any gap."""
    if not sdk_uuid:
        return None
    path = _codex_rollout_path(sdk_uuid)
    if path is None:
        return None
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            window = min(size, 256 * 1024)
            fh.seek(-window, os.SEEK_END)
            tail = fh.read().decode("utf-8", errors="replace")
    except OSError as exc:
        logger.debug("codex rollout tail failed %s: %s", path, exc)
        return None
    for line in reversed(tail.splitlines()):
        if '"token_count"' not in line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = obj.get("payload")
        info = payload.get("info") if isinstance(payload, dict) else None
        if not isinstance(info, dict):
            continue
        last = info.get("last_token_usage")
        used = last.get("total_tokens") if isinstance(last, dict) else None
        model_window = info.get("model_context_window")
        try:
            used_i = int(used)
            window_i = int(model_window)
        except (TypeError, ValueError):
            continue
        if used_i <= 0 or window_i <= 0:
            continue
        return used_i, window_i
    return None


def _effective_window(model: str | None, used: int) -> int:
    """Window for pct math: the model id when stamped; else inferred — a used
    count above 200K is proof of a 1M window (a 200K session can't exceed it)."""
    if model:
        return _context_window(model)
    return 1_000_000 if used > 200_000 else 200_000


def _context_pct_from_used_tokens(used_tokens: Any, model: str | None) -> float | None:
    """Pure: context percent from a pre-summed token count + model.

    Reads the `used_tokens` value the Stop hook stamps into sessions/<sid>.json
    (TASK-255). Honest-null when there is no usable count (TASK-192)."""
    try:
        used = int(used_tokens)
    except (TypeError, ValueError):
        return None
    if used <= 0:
        return None
    return round(min(100.0, used / _effective_window(model, used) * 100.0), 1)


def _context_pct_from_usage(usage: dict, model: str | None) -> float | None:
    """Pure: context-window percent from a transcript usage block + model.

    1M window for a `[1m]` model id, else 200K. Returns None when there is no
    usable token count — never a fabricated number (TASK-192)."""
    if not isinstance(usage, dict):
        return None
    used = sum(
        int(usage.get(k) or 0)
        for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    )
    if used <= 0:
        return None
    return round(min(100.0, used / _context_window(model) * 100.0), 1)


def _latest_transcript_usage(transcript_path: Path) -> dict | None:
    """Tail the in-tree snapshot transcript for the most recent usage block.

    Cheap (last 256 KB only), fail-open. Only Claude writes these snapshots,
    so non-Claude agents naturally yield no usage."""
    try:
        with transcript_path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            window = min(size, 256 * 1024)
            fh.seek(-window, os.SEEK_END)
            tail = fh.read().decode("utf-8", errors="ignore")
    except OSError:
        return None
    for line in reversed(tail.splitlines()):
        if '"usage"' not in line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = obj.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("usage"), dict):
            return msg["usage"]
        if isinstance(obj.get("usage"), dict):
            return obj["usage"]
    return None
