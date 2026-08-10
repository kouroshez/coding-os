"""Path resolution shared by every `cos` command that takes a project directory.

Leaf module: `--project-dir` resolution under `uv --directory`, the coding-os
self-init refusal, and the source-checkout root. Imports no command module.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click

# CODING_OS_ROOT is the source-checkout root — kept for dev-only operations; it
# is meaningless under a wheel install. The bundled DATA trees resolve via
# importlib so they are found under both src-layout and wheel installs (TASK-219).
CODING_OS_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_project_dir(raw: str) -> Path:
    """Resolve the `--project-dir` value to an absolute path.

    Handles the `uv run --directory <coding-os>` invocation pattern
    correctly: when uv changes cwd to the coding-os repo before launching
    Python, a default `.` would resolve to coding-os itself, silently
    initializing the coding-os repo instead of the user's project.

    Resolution order:
      1. If the raw value is NOT exactly "." (user passed an explicit path)
         → resolve relative to the current Python cwd.
      2. Otherwise, prefer the shell's `$PWD` env var (uv and most shells
         preserve it — it's the original invocation directory).
      3. Fall back to `os.getcwd()` for non-uv invocations.

    This is defensive — `Path(".").resolve()` alone is dangerous under
    `uv --directory` because uv rewrites cwd before Python starts.
    """
    if raw != ".":
        return Path(raw).resolve()

    shell_pwd = os.environ.get("PWD")
    if shell_pwd and Path(shell_pwd).is_dir():
        return Path(shell_pwd).resolve()
    return Path.cwd().resolve()


def _refuse_coding_os_self_init(project: Path) -> None:
    """Block init from running inside the coding-os repo itself.

    The coding-os source tree already contains `AGENTS.md`, `Makefile`,
    `docs/`, `core/` etc — running `init` against it scatters scaffold
    files across the repo and can overwrite real development docs.
    Detect this by checking for the telltale `src/core/thinking_os/server.py`
    file and refuse.
    """
    from cli._init_helpers import is_coding_os_source_tree

    if is_coding_os_source_tree(project):
        click.echo(
            f"\nERROR: Refusing to init inside the coding-os repo itself ({project}).\n"
            f"  This path contains src/core/thinking_os/server.py — it is the source tree.\n"
            f"  Initializing here would scatter scaffold files into the repo.\n\n"
            f"  Fix:\n"
            f"    cd /path/to/your/actual-project\n"
            f"    uv run --directory {project} python -m cli.main init \\\n"
            f'      --agent claude --project-dir "$(pwd)"\n\n'
            f"  Or use the alias:\n"
            f"    alias cos-init='uv run --directory {project} python -m cli.main init'\n"
            f'    cos-init --agent claude --project-dir "$(pwd)"\n',
            err=True,
        )
        sys.exit(1)
