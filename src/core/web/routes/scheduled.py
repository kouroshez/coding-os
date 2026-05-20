"""core.web.routes.scheduled — /api/scheduled/* hub endpoints."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter

_CORE_DIR = Path(__file__).resolve().parents[3]
_SCHEDULED_DIR = _CORE_DIR / "core" / "scheduled"
if str(_SCHEDULED_DIR) not in sys.path:
    sys.path.insert(0, str(_SCHEDULED_DIR))

from _state import read_registry, read_state  # type: ignore  # noqa: E402

router = APIRouter(prefix="/api/scheduled", tags=["scheduled"])
logger = logging.getLogger("codingos.web.scheduled")

_PLIST_DEST = Path.home() / "Library" / "LaunchAgents" / "com.codingos.nightly.plist"
_GLOBAL_SUMMARY = Path.home() / ".coding-os" / "scheduled" / "last_summary.json"


def _plist_installed() -> bool:
    return _PLIST_DEST.exists()


def _launchd_loaded() -> bool:
    try:
        result = subprocess.run(
            ["launchctl", "list", "com.codingos.nightly"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False
    except subprocess.TimeoutExpired:
        logger.debug("launchctl list timed out")
        return False


def _next_run_at() -> str | None:
    try:
        now = datetime.now()
        next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if now.hour >= 3:
            next_run = next_run + timedelta(days=1)
        return next_run.astimezone(timezone.utc).isoformat()
    except (ValueError, OSError) as exc:
        logger.debug("_next_run_at error: %s", exc)
        return None


@router.get("/status")
async def scheduled_status():
    """Return nightly cron status + per-project last_run.json contents."""
    projects_data = []
    for proj in read_registry():
        root = Path(proj.get("path", ""))
        state = read_state(root)
        projects_data.append(
            {
                "slug": proj.get("slug"),
                "path": proj.get("path"),
                "last_run_at": state.get("run_at"),
                "tasks": state.get("tasks", {}),
                "consecutive_failures": state.get("consecutive_failures", 0),
                "disabled_reason": state.get("disabled_reason"),
                "last_error": state.get("last_error"),
            }
        )

    global_summary: dict = {}
    if _GLOBAL_SUMMARY.exists():
        try:
            global_summary = json.loads(_GLOBAL_SUMMARY.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("could not read global summary: %s", exc)

    loaded = _launchd_loaded()
    return {
        "cron_a": {
            "installed": _plist_installed(),
            "loaded": loaded,
            "last_run_at": global_summary.get("run_at"),
            "next_run_at": _next_run_at() if loaded else None,
            "plist_path": str(_PLIST_DEST),
            "log_dir": str(Path.home() / ".coding-os" / "scheduled"),
        },
        "projects": projects_data,
    }


@router.get("/project/{slug}")
async def project_scheduled_status(slug: str):
    """Return last_run.json for a single project."""
    for proj in read_registry():
        if proj.get("slug") == slug:
            root = Path(proj.get("path", ""))
            state = read_state(root)
            return {"slug": slug, **state}
    return {"error": f"project {slug!r} not found in registry"}
