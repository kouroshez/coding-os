"""core.web.routes.scheduled — /api/scheduled/* hub endpoints."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

_CORE_DIR = Path(__file__).resolve().parents[3]
_CORE_PKG = _CORE_DIR / "core"
_SCHEDULED_DIR = _CORE_PKG / "scheduled"
for _p in (str(_CORE_PKG), str(_SCHEDULED_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _state import read_registry, read_state  # type: ignore  # noqa: E402
from scheduled.config import DEFAULTS, load_config, save_config  # type: ignore  # noqa: E402

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


def _root_for_slug(slug: str) -> Path | None:
    for proj in read_registry():
        if proj.get("slug") == slug:
            return Path(proj.get("path", ""))
    return None


class ScheduledConfigUpdate(BaseModel):
    enabled: bool | None = None
    hour: int | None = None
    decay_throttle_days: int | None = None
    learn_extract_min_outcomes: int | None = None
    responsive_extract_threshold: int | None = None


@router.get("/config/{slug}")
async def get_scheduled_config(slug: str):
    """Return the editable scheduled-maintenance config for one project."""
    root = _root_for_slug(slug)
    if root is None:
        return {"error": f"project {slug!r} not found in registry"}
    return {"slug": slug, "config": load_config(root), "defaults": DEFAULTS}


@router.patch("/config/{slug}")
async def patch_scheduled_config(slug: str, update: ScheduledConfigUpdate):
    """Persist edited scheduled config (cadence + responsive thresholds)."""
    root = _root_for_slug(slug)
    if root is None:
        return {"error": f"project {slug!r} not found in registry"}
    updates = {k: v for k, v in update.model_dump().items() if v is not None}
    saved = save_config(root, updates)
    return {"slug": slug, "config": saved}
