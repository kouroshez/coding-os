"""`cos adopt` — overlay coding-os onto an existing repo without touching user code.

Stack detection from build markers, then the same scaffold `cos init` runs, in
place and never wiping.
"""

from __future__ import annotations

import os
from pathlib import Path

import click

from cli._init_registries import (
    _enable_flag_help,
    _get_stack_registry,
    _module_flag_help,
    _profile_flag_help,
)
from cli._init_world import _detect_existing_install, _sync_missing
from cli.init_command import init

_STACK_MARKER_LANGUAGES: dict[str, str] = {
    # Build-manifest marker → base language. Resolved to that language's plain
    # stack via the registry below, so no stack id is ever hardcoded (Rule 11).
    "pyproject.toml": "python",
    "setup.py": "python",
    "requirements.txt": "python",
    "package.json": "typescript",
    "go.mod": "go",
    "Cargo.toml": "rust",
    "Gemfile": "ruby",
    "composer.json": "php",
    "pom.xml": "java",
    "build.gradle": "java",
}


def _detect_stacks_from_markers(path: Path) -> list[str]:
    """Resolve build-manifest markers in `path` to plain-stack ids via the
    registry — the brownfield-adopt stack proposal (no anatomy relocation)."""
    from cli.stack_registry import plain_stack_by_language

    registry = _get_stack_registry()
    profiles = {sid: registry[sid] for sid in registry}
    language_to_plain = plain_stack_by_language(profiles)
    detected: list[str] = []
    for marker, language in _STACK_MARKER_LANGUAGES.items():
        if not (path / marker).exists():
            continue
        stack = language_to_plain.get(language)
        if stack and stack not in detected:
            detected.append(stack)
    return detected


@click.command()
@click.option(
    "--agent",
    "-a",
    default=None,
    help="Agent adapter(s) to install, comma-separated (required with --yes).",
)
@click.option(
    "--template",
    "-t",
    multiple=True,
    help="Stack template(s) to record — overrides build-marker auto-detection.",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Non-interactive: adopt into the current directory using flags + defaults.",
)
@click.option("--git/--no-git", default=True, help="Run `git init` if the repo isn't already one.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format.",
)
@click.option(
    "--no-register",
    is_flag=True,
    default=False,
    help="Skip writing this project to the global registry (sandbox fixtures).",
)
@click.option(
    "--index/--no-index",
    "do_index",
    default=True,
    help="Seed the doc-search index after adopt (--no-index for fast / CI runs).",
)
@click.option(
    "--disable-module",
    "disable_module",
    multiple=True,
    help=_module_flag_help(),
)
@click.option(
    "--profile",
    "profile",
    default=None,
    help=_profile_flag_help(),
)
@click.option(
    "--enable-module",
    "enable_module",
    multiple=True,
    help=_enable_flag_help(),
)
@click.pass_context
def adopt(
    ctx: click.Context,
    agent: str | None,
    template: tuple[str, ...],
    yes: bool,
    git: bool,
    output_format: str,
    no_register: bool,
    do_index: bool,
    disable_module: tuple[str, ...],
    profile: str | None,
    enable_module: tuple[str, ...],
) -> None:
    """Overlay coding-os onto an existing repo without touching user code.

    Adds .coding-os/ state, adapter dirs and AGENTS.md in place, auto-detecting
    stacks from build markers (pyproject.toml / package.json / go.mod / …). An
    already-adopted repo pivots to the idempotent sync path instead of re-installing.
    """
    target = Path(os.environ.get("PWD") or os.getcwd()).resolve()

    # Already adopted → idempotent sync (same path as a bare re-`cos init`).
    if _detect_existing_install(target) is not None:
        if output_format == "text":
            click.echo(f"coding-os already present at {target} — syncing missing components.")
        _sync_missing(target, output_format=output_format)
        return

    # Propose stacks from build markers unless the caller pinned --template.
    if not template:
        detected = _detect_stacks_from_markers(target)
        if detected and output_format == "text":
            click.echo(f"Detected stacks: {', '.join(detected)}")
        template = tuple(detected)

    # Reuse the init scaffold in place — name/project_dir unset ⇒ current dir,
    # force unset ⇒ no wipe, so pre-existing user files are never overwritten.
    ctx.invoke(
        init,
        agent=agent,
        template=template,
        adopt=True,
        yes=yes,
        git=git,
        output_format=output_format,
        no_register=no_register,
        do_index=do_index,
        disable_module=disable_module,
        profile=profile,
        enable_module=enable_module,
    )
