"""Project commands a consumer runs through cos: run, memory and file-size checks, changes.log.

Consumers ship no Makefile, so the stack commands in .coding-os.yaml and the
project checks the shipped rules name are reached here, from any subfolder.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import click

from cli._skill_project import _find_project_root, _load_project_config

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "core" / "scripts"


@click.command("run")
@click.argument("name", required=False)
def run_cmd(name: str | None) -> None:
    """Run a stack command from .coding-os.yaml (e.g. lint-backend); with no name, list them."""
    root = _find_project_root()
    commands: dict[str, str] = _load_project_config(root).get("commands") or {}
    if name is None:
        if not commands:
            click.echo("No stack commands in .coding-os.yaml: this project's stacks declare none.")
        for command_name, shell in commands.items():
            click.echo(f"{command_name:<28} {shell}")
        return
    if name not in commands:
        known = ", ".join(commands) or "none"
        raise click.ClickException(f"unknown command '{name}' (known: {known})")
    sys.exit(subprocess.run(commands[name], shell=True, cwd=root).returncode)


def _run_script(script: str) -> None:
    root = _find_project_root()
    sys.exit(subprocess.run([sys.executable, str(_SCRIPTS_DIR / script)], cwd=root).returncode)


@click.command("memory-lint")
def memory_lint_cmd() -> None:
    """Check .agents/memory: every note indexed once, links resolve, MEMORY.md within the load limit."""
    _run_script("memory_lint.py")


@click.command("check-file-size")
def check_file_size_cmd() -> None:
    """Fail when a source file passes the 500-line backstop; warn from 400."""
    _run_script("check_file_size.py")


@click.command("log-write")
@click.option(
    "--type",
    "entry_type",
    required=True,
    type=click.Choice(["feat", "fix", "refactor", "docs", "test", "infra"]),
    help="Entry type.",
)
@click.option("--msg", required=True, help="One-line title.")
@click.option("--what", default="", help="Impact of the change.")
@click.option("--files", default="", help="Files touched, comma separated.")
@click.option("--task", default="", help="Task number, e.g. 014.")
def log_write_cmd(entry_type: str, msg: str, what: str, files: str, task: str) -> None:
    """Append one structured entry to changes.log (the only way to write it)."""
    for option, value in (("--msg", msg), ("--what", what), ("--files", files)):
        if "\n" in value or "\r" in value:
            raise click.BadParameter("must be a single line", param_hint=option)
    if task and not re.fullmatch(r"(TASK-)?[0-9]+", task):
        raise click.BadParameter("a task number such as 014 or TASK-014", param_hint="--task")
    root = _find_project_root()
    script = _SCRIPTS_DIR / "log-write.sh"
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in ("TASK", "TYPE", "MSG", "WHAT", "FILES")
    }
    sys.exit(
        subprocess.run(
            ["bash", str(script), task, entry_type, msg, what, files], cwd=root, env=environment
        ).returncode
    )


@click.command("log-latest")
@click.argument("count", default="1")
def log_latest_cmd(count: str) -> None:
    """Show the last COUNT changes.log entries (a number, or `all` for today's)."""
    if not (re.fullmatch(r"[0-9]+", count) or count == "all"):
        raise click.BadParameter("a whole number or 'all'", param_hint="COUNT")
    root = _find_project_root()
    sys.exit(
        subprocess.run(["bash", str(_SCRIPTS_DIR / "log-latest.sh"), count], cwd=root).returncode
    )


@click.command("log-search")
@click.argument("query")
@click.argument("count", default="10")
def log_search_cmd(query: str, count: str) -> None:
    """Search changes.log for entries matching QUERY (case-insensitive)."""
    root = _find_project_root()
    sys.exit(
        subprocess.run(
            ["bash", str(_SCRIPTS_DIR / "log-search.sh"), query, count], cwd=root
        ).returncode
    )
