"""graph_os — whether git tracks files under a folder: a source folder named like build output stays."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("graph_os.ingest.tracked")

GIT_TIMEOUT_SECONDS = 10

_CACHE: dict[tuple[str, str, int], bool] = {}


def is_tracked_dir(root: Path, rel_dir: str) -> bool:
    """Whether git tracks any file under `rel_dir`; False outside a repo or without git."""
    key = (str(root), rel_dir, _mtime(_index_path(root)))
    if key not in _CACHE:
        _CACHE[key] = _git_tracks(root, rel_dir)
    return _CACHE[key]


def _git_tracks(root: Path, rel_dir: str) -> bool:
    try:
        listed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", rel_dir],
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("git ls-files unavailable for %s: %s", rel_dir, exc)
        return False
    return listed.returncode == 0 and bool(listed.stdout)


def _index_path(root: Path) -> Path:
    # A worktree or submodule keeps a `.git` file naming its real git directory.
    dot_git = root / ".git"
    if dot_git.is_file():
        try:
            pointer = dot_git.read_text(encoding="utf-8").strip()
        except OSError:
            return dot_git
        if pointer.startswith("gitdir:"):
            git_dir = Path(pointer.removeprefix("gitdir:").strip())
            return (git_dir if git_dir.is_absolute() else root / git_dir) / "index"
    return dot_git / "index"


def _mtime(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0
