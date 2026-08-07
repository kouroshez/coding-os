from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class SettingsConflictError(ValueError):
    pass


def project_settings_path(project_root: Path | None = None) -> Path:
    if project_root is not None:
        return project_root.resolve() / ".coding-os" / "hub-settings.json"
    state_dir = os.environ.get("COS_STATE_DIR")
    if state_dir:
        return Path(state_dir).resolve() / "hub-settings.json"
    configured_root = os.environ.get("COS_PROJECT_ROOT")
    root = Path(configured_root).resolve() if configured_root else Path.cwd().resolve()
    return root / ".coding-os" / "hub-settings.json"


def read_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SettingsConflictError(
            f"{path} is present but unreadable; refusing to overwrite it: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise SettingsConflictError(f"{path} must contain a JSON object")
    return data


def write_settings(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".hub-settings.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


@contextlib.contextmanager
def settings_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name("hub-settings.lock")
    with lock_path.open("w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
