"""Core-version stamp — records which coding-os core scaffolded/updated a
consumer project so `cos doctor` can warn on drift. Consumers pin to core
via live symlinks with no version signal (D6); a breaking hook/MCP change
otherwise breaks them silently on `cos update`. TASK-078."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path

logger = logging.getLogger(__name__)

STAMP_FILENAME = "core-version.json"
PACKAGE_NAME = "coding-os"
PYPI_RELEASE_URL = f"https://pypi.org/pypi/{PACKAGE_NAME}/json"
UPGRADE_COMMAND = f"uv tool upgrade {PACKAGE_NAME}"
EDITABLE_UPGRADE_COMMAND = "git pull && uv tool install --editable ."


def current_core_version() -> str:
    try:
        return _pkg_version(PACKAGE_NAME)
    except PackageNotFoundError:
        return "unknown"


def latest_published_version(*, timeout: float = 2.5) -> str | None:
    """Newest coding-os on PyPI, or None when the index is unreachable."""
    # One request, hard-capped: `cos update` must stay usable on a plane. Every
    # failure mode — offline, proxy, index outage, malformed body — returns None
    # so the caller says nothing rather than blocking the update it was asked for.
    try:
        with urllib.request.urlopen(PYPI_RELEASE_URL, timeout=timeout) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.debug("release check skipped: %s", exc)
        return None
    latest = (payload.get("info") or {}).get("version")
    return latest if isinstance(latest, str) and latest else None


def upgrade_command() -> str:
    """The command that actually moves the installed coding-os version."""
    # Deliberately not auto-detected. Reading `direct_url.json` to tell an
    # editable checkout from a PyPI install resolves to a different distribution
    # depending on cwd and sys.path — and upgrade advice that is wrong half the
    # time costs more than one extra clause naming the checkout case.
    return UPGRADE_COMMAND


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
