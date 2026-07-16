"""Locate the bundled data trees (core/, adapters/, templates/, scripts/) at
runtime — correctly under BOTH a src-layout editable install and a built wheel.

The legacy `Path(__file__).parent.parent.parent / "src" / "core"` resolves the
*source checkout* and breaks once `cos` is pip/uvx-installed (site-packages has
no `src/` tree). Here we resolve relative to the installed `core` package so the
same code path works in either install mode. TASK-219.
"""

from __future__ import annotations

import importlib.util
import os
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


# ---------------------------------------------------------------------------
# Out-of-tree plugin overlay (community stacks / adapters) — mirrors the
# community-skill model (skill_commands.user_skills_dir / $COS_USER_SKILLS_DIR).
# A third party drops a stack at $COS_USER_TEMPLATES_DIR/<id>/stack.yaml or an
# adapter at $COS_USER_ADAPTERS_DIR/<id>/adapter.yaml and the registries
# discover it WITHOUT forking the repo. The bundled tree always wins on an id
# collision (a community plugin may not shadow a core stack/adapter).
# ---------------------------------------------------------------------------
def user_templates_dir() -> Path:
    """Out-of-tree community-stack root. Override with $COS_USER_TEMPLATES_DIR."""
    override = os.environ.get("COS_USER_TEMPLATES_DIR")
    return Path(override) if override else Path.home() / ".coding-os" / "templates"


def user_adapters_dir() -> Path:
    """Out-of-tree community-adapter root. Override with $COS_USER_ADAPTERS_DIR."""
    override = os.environ.get("COS_USER_ADAPTERS_DIR")
    return Path(override) if override else Path.home() / ".coding-os" / "adapters"


def user_modules_dir() -> Path:
    """Out-of-tree community-module (subsystem) root. Override with $COS_USER_MODULES_DIR.

    A plugin author drops a `<id>.yaml` here with a `modules:` block and
    load_subsystems() merges it over the core registry WITHOUT forking the repo
    (the bundled tree always wins on an id collision)."""
    override = os.environ.get("COS_USER_MODULES_DIR")
    return Path(override) if override else Path.home() / ".coding-os" / "modules.d"


def overlay_module_files() -> tuple[Path, ...]:
    """User-overlay module YAML files that actually exist (see overlay_template_dirs)."""
    d = user_modules_dir()
    return tuple(sorted(d.glob("*.yaml"))) if d.is_dir() else ()


def overlay_template_dirs() -> tuple[Path, ...]:
    """User-overlay template dirs that actually exist — empty in CI / a fresh
    install, so default-resolving them is a no-op (no test pollution)."""
    d = user_templates_dir()
    return (d,) if d.is_dir() else ()


def overlay_adapter_dirs() -> tuple[Path, ...]:
    """User-overlay adapter dirs that actually exist (see overlay_template_dirs)."""
    d = user_adapters_dir()
    return (d,) if d.is_dir() else ()
