"""`cos materialize-file <path>` — replace a symlink with a writable copy.

Fine-grained alternative to `cos materialize` (which copies everything).
Useful when a user wants to customize a single policy doc (e.g.
workflow-guide.md) without losing the ability to `cos update` the rest of
the symlinks.

After materialize:
  - the path is a regular file, safe to edit
  - `cos update` will NOT touch it (update only manages symlinks)
  - `cos doctor` still passes
"""

from __future__ import annotations

from pathlib import Path

import click


@click.command("materialize-file")
@click.argument("rel_path")
@click.option("--project-dir", "-d", default=".", help="Project directory")
@click.option("--force", is_flag=True, default=False, help="Replace if already a regular file")
def materialize_file(rel_path: str, project_dir: str, force: bool) -> None:
    """Replace the symlink at REL_PATH with a real copy of its target.

    REL_PATH is relative to the project root.

    Examples:
      cos materialize-file .claude/skills/thinking_os/SKILL.md
      cos materialize-file docs/workflow/workflow-guide.md
    """
    project = Path(project_dir).resolve()
    target = project / rel_path

    if not target.exists() and not target.is_symlink():
        raise click.ClickException(f"Path does not exist: {rel_path}")

    if target.is_symlink():
        real = target.resolve()
        if not real.exists():
            raise click.ClickException(f"Dangling symlink — target {real} no longer exists")
        content_source = real
    else:
        if not force:
            raise click.ClickException(
                f"{rel_path} is already a regular file. Use --force to overwrite."
            )
        content_source = target

    # Write into a sibling tempfile, then replace atomically.
    data = content_source.read_bytes()
    if target.is_symlink():
        target.unlink()
    tmp = target.with_suffix(target.suffix + ".materializetmp")
    tmp.write_bytes(data)
    tmp.replace(target)

    click.echo(
        f"Materialized {rel_path}\n"
        f"  was:  symlink → {content_source}\n"
        f"  now:  regular file ({len(data)} bytes)\n"
        f"  note: `cos update` will no longer manage this file."
    )
