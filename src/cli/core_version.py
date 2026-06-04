"""Core-version stamp — records which coding-os core scaffolded/updated a
consumer project so `cos doctor` can warn on drift. Consumers pin to core
via live symlinks with no version signal (D6); a breaking hook/MCP change
otherwise breaks them silently on `cos update`. TASK-078."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

STAMP_FILENAME = "core-version.json"


def current_core_version() -> str:
    try:
        return _pkg_version("coding-os")
    except PackageNotFoundError:
        return "unknown"


def stamp_core_version(state_dir: Path, *, now_iso: str | None = None) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / STAMP_FILENAME
    payload = {
        "core_version": current_core_version(),
        "stamped_at": now_iso or datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def read_stamped_version(state_dir: Path) -> str | None:
    try:
        raw = (state_dir / STAMP_FILENAME).read_text(encoding="utf-8")
        value = json.loads(raw).get("core_version")
        return value if isinstance(value, str) else None
    except (OSError, ValueError):
        return None
