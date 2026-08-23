"""State read/write for scheduled job runs."""

from __future__ import annotations

import fcntl
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("codingos.scheduled.state")

_STATE_FILE = "last_run.json"
_SCHEDULED_DIR = "scheduled"


def state_dir(project_root: Path) -> Path:
    return project_root / ".coding-os" / _SCHEDULED_DIR


def state_path(project_root: Path) -> Path:
    return state_dir(project_root) / _STATE_FILE


def read_state(project_root: Path) -> dict:
    """Read last_run.json for a project; returns {} if missing."""
    path = state_path(project_root)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("read_state failed for %s: %s", project_root, exc)
        return {}


def write_state(project_root: Path, state: dict) -> None:
    """Write last_run.json atomically (flock-protected)."""
    sdir = state_dir(project_root)
    sdir.mkdir(parents=True, exist_ok=True)
    path = state_path(project_root)
    lock_path = path.with_suffix(".lock")

    try:
        with open(lock_path, "w") as lock_f:
            fcntl.flock(lock_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(state, indent=2, default=str))
                tmp.replace(path)
            finally:
                fcntl.flock(lock_f, fcntl.LOCK_UN)
    except BlockingIOError:
        logger.warning("write_state: lock contention for %s — skipping write", project_root)
    except OSError as exc:
        logger.warning("write_state failed for %s: %s", project_root, exc)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def days_since_marker(marker_path: Path) -> float | None:
    """Return days since marker file was last modified; None if missing."""
    if not marker_path.exists():
        return None
    try:
        mtime = marker_path.stat().st_mtime
        elapsed = datetime.now(timezone.utc).timestamp() - mtime
        return max(0.0, elapsed / 86400.0)
    except OSError as exc:
        logger.debug("days_since_marker error: %s", exc)
        return None


def touch_marker(marker_path: Path) -> None:
    """Write current ISO timestamp to marker file."""
    try:
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(now_iso())
    except OSError as exc:
        logger.warning("touch_marker failed for %s: %s", marker_path, exc)


def read_registry(hub_state_dir: Path | None = None) -> list[dict]:
    """Read ~/.coding-os/registry.json → list of {slug, path} dicts.

    Fallback: COS_PROJECT_ROOT env → [{slug: 'local', path: cwd}].
    """
    candidates: list[Path] = []
    if hub_state_dir:
        candidates.append(hub_state_dir / "registry.json")
    candidates.append(Path.home() / ".coding-os" / "registry.json")

    for reg_path in candidates:
        if reg_path.exists():
            try:
                data = json.loads(reg_path.read_text())
                projects = data.get("projects", [])
                if projects:
                    return projects
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("read_registry failed for %s: %s", reg_path, exc)

    env_root = os.environ.get("COS_PROJECT_ROOT", "")
    if env_root:
        logger.info("registry not found; using COS_PROJECT_ROOT=%s", env_root)
        return [{"slug": Path(env_root).name, "path": env_root}]

    cwd = str(Path.cwd())
    logger.info("registry not found; falling back to cwd=%s", cwd)
    return [{"slug": Path(cwd).name, "path": cwd}]
