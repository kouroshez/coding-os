"""Locate the bundled data trees (core/, adapters/, templates/, scripts/) at
runtime — correctly under BOTH a src-layout editable install and a built wheel.

The legacy `Path(__file__).parent.parent.parent / "src" / "core"` resolves the
*source checkout* and breaks once `cos` is pip/uvx-installed (site-packages has
no `src/` tree). Here we resolve relative to the installed `core` package so the
same code path works in either install mode. TASK-219.
"""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def data_root() -> Path:
    """Directory that CONTAINS the core/adapters/templates/scripts trees.

    Source (editable) install -> `<repo>/src`; wheel install -> `site-packages`.
    Both place `core/` directly inside this dir, so `data_root()/ "core"` etc.
    resolve identically.
    """
    spec = importlib.util.find_spec("core")
    if spec is not None and spec.origin:
        # .../<root>/core/__init__.py  ->  <root>
        return Path(spec.origin).resolve().parent.parent
    # Fallback for an unusual import state: src/cli/_resources.py -> src/
    return Path(__file__).resolve().parent.parent


def core_dir(*parts: str) -> Path:
    """Path under the bundled `core` tree (hooks, commands, skills, rules, ...)."""
    return data_root().joinpath("core", *parts)


def adapters_dir(*parts: str) -> Path:
    """Path under the bundled `adapters` tree."""
    return data_root().joinpath("adapters", *parts)


def templates_dir(*parts: str) -> Path:
    """Path under the bundled `templates` tree (per-stack scaffolds)."""
    return data_root().joinpath("templates", *parts)


def scripts_dir(*parts: str) -> Path:
    """Path under the bundled `scripts` tree (git-hook bodies, installers)."""
    return data_root().joinpath("scripts", *parts)
