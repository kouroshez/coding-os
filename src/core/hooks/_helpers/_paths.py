"""Shared project-root resolver for hook helpers (no DB import on the hot path).

Hooks fire on every Write/Edit; importing thinking_os.database costs ~20-60ms.
Since cos-env.sh already sets COS_STATE_DIR (absolute), tiers 1-2 answer without
that import — tier 3 (lazy database.project_root) only runs in the rare case
where neither env var is set, and tier 4 (cwd) is the fail-open last resort.
"""

from __future__ import annotations

import os
from pathlib import Path


def resolve_project_root() -> Path:
    explicit = os.environ.get("COS_PROJECT_ROOT")
    if explicit:
        return Path(explicit).resolve()

    state = os.environ.get("COS_STATE_DIR")
    if state:
        state_path = Path(state)
        if state_path.is_absolute():
            parent = state_path.resolve().parent
            # $HOME hard-stop: COS_STATE_DIR == $HOME/.coding-os is the global
            # hub (set by `cos hub`), not a project root. Mirrors the boundary
            # in database.project_root() + cos-env.sh::_cos_find_project_root.
            try:
                home = Path.home().resolve()
            except (OSError, RuntimeError):
                home = None
            if home is None or parent != home:
                return parent

    try:
        from thinking_os.database import project_root as _resolve_root  # type: ignore

        return _resolve_root()
    except ImportError:
        return Path.cwd().resolve()
