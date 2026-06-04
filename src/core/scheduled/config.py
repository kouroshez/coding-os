"""Scheduled-maintenance config — cron cadence + responsive thresholds.

Per-project JSON at ``<proj>/.coding-os/scheduled/config.json`` read by the
nightly daemon, the responsive session-end trigger, and the Hub
(``GET``/``PUT /api/scheduled/config``). Missing keys fall back to defaults so
an absent file behaves exactly as the old hardcoded constants did.

Contract: docs/engineering/scheduled-jobs.md § Configurable cadence.
"""

from __future__ import annotations

import json
from pathlib import Path

from scheduled._state import state_dir

_CONFIG_FILE = "config.json"

DEFAULTS: dict[str, object] = {
    "enabled": True,
    "hour": 3,
    "decay_throttle_days": 7,
    "learn_extract_min_outcomes": 3,
    "responsive_extract_threshold": 5,
}

# (key, lo, hi) bounds for integer fields — values are clamped on save.
_INT_BOUNDS: dict[str, tuple[int, int]] = {
    "hour": (0, 23),
    "decay_throttle_days": (1, 365),
    "learn_extract_min_outcomes": (1, 1000),
    "responsive_extract_threshold": (1, 1000),
}


def config_path(project_root: Path | str) -> Path:
    return state_dir(Path(project_root)) / _CONFIG_FILE


def _coerce(key: str, value: object) -> object:
    if key == "enabled":
        return bool(value)
    lo, hi = _INT_BOUNDS[key]
    try:
        return max(lo, min(hi, int(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULTS[key]


def load_config(project_root: Path | str) -> dict:
    """Return the project's scheduled config, defaults filled for missing keys."""
    cfg = dict(DEFAULTS)
    path = config_path(project_root)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cfg
    if isinstance(raw, dict):
        for key in DEFAULTS:
            if key in raw:
                cfg[key] = _coerce(key, raw[key])
    return cfg


def save_config(project_root: Path | str, updates: dict) -> dict:
    """Merge validated updates into the project's config and persist atomically."""
    cfg = load_config(project_root)
    for key, value in updates.items():
        if key in DEFAULTS:
            cfg[key] = _coerce(key, value)
    path = config_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return cfg
