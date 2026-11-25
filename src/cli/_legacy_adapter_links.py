"""Clear what older installs linked where an agent no longer reads it."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import click

from cli._resources import overlay_adapter_dirs
from cli._update_manifest import ADAPTERS_DIR, CODING_OS_ROOT, _load_config
from cli.adapter_registry import load_adapter_registry


def _drop_unread_adapter_links(project: Path) -> None:
    # Older installs linked a commands dir an agent never reads, and a per-agent
    # skills dir an agent now reads from a shared root; clear what cos put there.
    from cli._skill_project import user_skills_dir

    owners = (CODING_OS_ROOT.resolve(), user_skills_dir().resolve())
    registry = load_adapter_registry(ADAPTERS_DIR, overlay_dirs=overlay_adapter_dirs())
    for agent in _load_config(project).get("agents") or []:
        adapter = registry.get(agent)
        if adapter is None or not adapter.hooks_dir:
            continue
        agent_dir = project / Path(adapter.hooks_dir).parent
        legacy = []
        if not adapter.commands_dir:
            legacy.append(agent_dir / "commands")
        if adapter.skills_dir and project / adapter.skills_dir != agent_dir / "skills":
            legacy.append(agent_dir / "skills")
        for folder in legacy:
            # A committed link could aim the folder anywhere; act only inside the project.
            if folder.is_dir() and folder.resolve().is_relative_to(project.resolve()):
                _drop_cos_links(folder, owners)


def _cos_link(link: Path, owners: tuple[Path, ...]) -> bool:
    if not link.is_symlink():
        return False
    target = Path(os.path.realpath(link))
    return any(target.is_relative_to(owner) for owner in owners)


def _drop_cos_links(folder: Path, owners: tuple[Path, ...]) -> None:
    for entry in sorted(folder.iterdir()):
        if entry.is_symlink():
            if _cos_link(entry, owners):
                entry.unlink()
            continue
        if not entry.is_dir():
            continue
        for child in entry.iterdir():
            if _cos_link(child, owners):
                child.unlink()
        with contextlib.suppress(OSError):
            entry.rmdir()
        if entry.is_dir():
            rel = entry.relative_to(folder.parent.parent)
            click.echo(
                f"  {rel} is yours and stays; move it to the shared skills dir to list it once"
            )
    with contextlib.suppress(OSError):
        folder.rmdir()
