"""hub_adapter_manifest — discover adapter rows for Hub board API."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Fallback when adapters/ is missing (e.g. broken checkout).
_BOARD_DEFAULTS: dict[str, dict[str, str]] = {
    "claude": {"glyph": "Cl", "color": "#d97706"},
    "codex": {"glyph": "Cx", "color": "#0891b2"},
}


def _coding_os_repo_root() -> Path:
    env = os.environ.get("COS_CODING_OS_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    # src/core/board_os/this_file.py → parents[3] == repo root
    return Path(__file__).resolve().parents[3]


def _adapters_dir() -> Path:
    return _coding_os_repo_root() / "src" / "adapters"


def _scan_manifest_mtime(adapters: Path) -> float:
    """Max mtime of */adapter.yaml — cheap cache invalidation."""
    best = 0.0
    if not adapters.is_dir():
        return best
    try:
        best = max(best, adapters.stat().st_mtime)
    except OSError as exc:
        logger.debug("adapters dir stat failed: %s", exc)
    for child in adapters.iterdir():
        if not child.is_dir() or child.name.startswith("_"):
            continue
        yml = child / "adapter.yaml"
        if not yml.is_file():
            continue
        try:
            best = max(best, yml.stat().st_mtime)
        except OSError as exc:
            logger.debug("adapter yaml stat failed %s: %s", yml, exc)
    return best


def _fallback_tuple_rows() -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for aid, ui in sorted(_BOARD_DEFAULTS.items()):
        rows.append(
            {
                "id": aid,
                "label": aid,
                "glyph": ui["glyph"],
                "color": ui["color"],
                "session": f"ses-{aid}",
            }
        )
    return tuple(rows)


@lru_cache(maxsize=8)
def _cached_rows(cache_key: tuple[str, float]) -> tuple[dict[str, Any], ...]:
    """Internal: (adapters_dir_str, mtime) -> immutable rows."""
    adapters = Path(cache_key[0])
    rows: list[dict[str, Any]] = []
    if not adapters.is_dir():
        return _fallback_tuple_rows()

    for child in sorted(adapters.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        yml = child / "adapter.yaml"
        if not yml.is_file():
            continue
        try:
            raw = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            logger.debug("skip unreadable adapter yaml %s: %s", yml, exc)
            continue
        if not isinstance(raw, dict):
            continue
        aid = str(raw.get("id") or child.name)
        label = str(raw.get("label") or aid)
        presence = raw.get("presence") or {}
        if not isinstance(presence, dict):
            presence = {}
        glyph = str(presence.get("hub_glyph") or "").strip()
        color = str(presence.get("hub_color") or "").strip()
        defaults = _BOARD_DEFAULTS.get(aid, {})
        if not glyph:
            glyph = defaults.get("glyph") or (aid[:2].title() if len(aid) >= 2 else aid.upper())
        if len(glyph) > 3:
            glyph = glyph[:3]
        if not color or not color.startswith("#"):
            color = defaults.get("color") or "#64748b"
        rows.append(
            {
                "id": aid,
                "label": label,
                "glyph": glyph,
                "color": color,
                "session": f"ses-{aid}",
            }
        )
    if not rows:
        return _fallback_tuple_rows()
    return tuple(rows)


def list_agent_manifest_rows() -> list[dict[str, Any]]:
    """Return adapter rows for the Hub board (newest adapters/*.yaml wins)."""
    adapters = _adapters_dir()
    mt = _scan_manifest_mtime(adapters)
    key = (str(adapters), round(mt, 6))
    rows = _cached_rows(key)
    return [dict(r) for r in rows]


def list_agent_ids() -> list[str]:
    """Canonical adapter ids — the SSOT scanned from src/adapters (fallback: board defaults)."""
    try:
        return [str(r["id"]) for r in list_agent_manifest_rows() if r.get("id")]
    except Exception as exc:  # pragma: no cover - scanner already fails soft
        logger.debug("list_agent_ids fallback to board defaults: %s", exc)
        return list(_BOARD_DEFAULTS)


def invalidate_agent_manifest_cache() -> None:
    """Test hook: clear lru_cache after mutating adapters under tmp paths."""
    _cached_rows.cache_clear()
