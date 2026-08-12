"""Render the human-facing result of `cos init` — the completion panel.

One reason to change: what a person needs to see and do the moment a project
finishes scaffolding. Kept out of init_command.py because that module owns the
decision flow, and the two change for entirely different reasons.
"""

from __future__ import annotations

import platform
from pathlib import Path

import click

from cli._init_registries import (
    CONFIG_FILE,
    STATE_DIR,
    _example_swimlane,
    _get_stack_registry,
)
from cli.core_version import current_core_version, upgrade_command


def print_git_result(git_result, commit_result, hooks_result) -> None:
    if git_result.ran:
        click.echo("  git: initialized")
        if commit_result.committed:
            click.echo("  git: baseline commit created")
        elif commit_result.error:
            click.echo(f"  git: WARN baseline commit failed — {commit_result.error}")
        if hooks_result.installed:
            click.echo(f"  git: hooks installed ({', '.join(hooks_result.installed)})")
        elif hooks_result.error:
            click.echo(f"  git: WARN hooks not installed — {hooks_result.error}")
    elif git_result.skipped_reason:
        click.echo(f"  git: skipped ({git_result.skipped_reason})")
    elif git_result.error:
        click.echo(f"  git: WARN {git_result.error}")


def print_completion_panel(
    project: Path,
    *,
    agents: list[str],
    templates: tuple[str, ...],
    files_created: int,
    disabled_modules: list[str],
) -> None:
    click.echo("\ncoding-os initialized successfully!")
    click.echo(f"  Version:  {current_core_version()}")
    click.echo(f"  Path:     {project}")
    click.echo(f"  Files:    {files_created}")
    click.echo(f"  Config:   {CONFIG_FILE}")
    click.echo(f"  State:    {STATE_DIR}/")
    click.echo("  Makefile: make help")
    # The upgrade line is the point of having a panel at all: this is the one
    # moment the user is looking, and `cos update` alone never moves the version
    # — it re-links a project against the core already installed.
    click.echo(f"  Upgrade:  {upgrade_command()}   then `cos update` in each project")
    click.echo("  Health:   cos doctor            Hub: cos hub start")

    click.echo("\nQuick start (no Hub required — this all runs from the CLI):")
    click.echo(f"  cd {project.name} && {agents[0] if agents else '<your agent>'}")
    if "tasks" in disabled_modules:
        click.echo("  cos module list        # Subsystems on here (the task board is off)")
    else:
        click.echo("  cos daily              # Project status + today's tasks")
        click.echo(
            f'  cos task-create --title "First task" --swimlane {_example_swimlane(project)} '
            '--kind chore --outcome "Walk the CLI loop end to end" --ready'
        )
        click.echo("  cos task-start <ID>    # Guide: docs/workflow/workflow-guide.md")

    if not templates:
        available = sorted(_get_stack_registry().keys())
        click.echo(
            "\n  WARN: No stack template selected.\n"
            "  AGENTS.md has placeholder routing — agent works but lacks domain rules,\n"
            "  verify commands, and engineering guidelines.\n"
            "  Add a stack now:  cos add-stack <id>\n"
            f"  Available stacks: {', '.join(available)}"
        )

    if platform.system() == "Darwin":
        click.echo("\nNightly maintenance (optional):")
        click.echo("  cos cron install  # launchd job — decay, learn, routing (daily 03:00)")
