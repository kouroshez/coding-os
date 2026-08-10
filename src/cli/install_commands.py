"""Install-lifecycle commands: add-adapter, codex-mcp-install, health, materialize, eject.

Everything that mutates or inspects an already-initialised project's install.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

import click

from cli._cli_paths import CODING_OS_ROOT, _resolve_project_dir
from cli._init_helpers import ensure_agents_md, ensure_entrypoint_symlink
from cli._init_registries import (
    ADAPTERS_DIR,
    CONFIG_FILE,
    CORE_DIR,
    STATE_DIR,
    VALID_AGENTS,
    _get_adapter_registry,
)
from cli._init_scaffold import _run_adapter_install
from cli._init_world import _build_world, _load_config, _save_config
from cli._resources import core_dir
from cli.adapter_registry import load_adapter_registry


@click.command("add-adapter")
@click.argument("agent", type=click.Choice(VALID_AGENTS))
@click.option("--project-dir", "-d", default=".", help="Project directory")
def add_adapter(agent: str, project_dir: str) -> None:
    """Add an additional agent adapter to the project."""
    project = _resolve_project_dir(project_dir)
    config = _load_config(project)

    if not config:
        click.echo("ERROR: No .coding-os.yaml found. Run 'coding-os init' first.", err=True)
        sys.exit(1)

    agents = config.get("agents", [])
    if agent in agents:
        click.echo(f"Adapter '{agent}' is already installed.")
        return

    click.echo(f"Adding {agent} adapter...")
    _run_adapter_install(agent, project)

    agents.append(agent)
    config["agents"] = agents
    _save_config(project, config)
    click.echo(f"  Updated {CONFIG_FILE}")

    # AGENTS.md is the canonical per-project instruction file (read by both
    # Claude and Codex). `cos init` generates it, but older projects or
    # partial installs may be missing it — fill the gap so the newly added
    # adapter has something to read on first session.
    templates = tuple(config.get("templates", []) or [])
    world = _build_world(agent, templates, project)
    if ensure_agents_md(project, world):
        click.echo("  Generated AGENTS.md")

    entrypoint = _get_adapter_registry()[agent].entrypoint_file
    if ensure_entrypoint_symlink(project, entrypoint):
        click.echo(f"  Linked {entrypoint} → AGENTS.md")


@click.command("codex-mcp-install")
@click.option(
    "--config",
    "config_path",
    default=None,
    help="Codex config file (default: ./.codex/config.toml)",
)
@click.option(
    "--global",
    "global_scope",
    is_flag=True,
    default=False,
    help="Write to ~/.codex/config.toml instead of the project-local .codex/config.toml",
)
@click.option("--dry-run", is_flag=True, default=False, help="Print the snippet without writing")
def codex_mcp_install(config_path: str | None, global_scope: bool, dry_run: bool) -> None:
    """Register the coding-os MCP server in Codex config.

    Codex CLI supports both user-level ~/.codex/config.toml and trusted
    project overrides in .codex/config.toml. This command defaults to the
    project-local config so coding-os MCP stays scoped to the current repo;
    pass `--global` only when you explicitly want the server available
    everywhere. Safe to re-run — it repairs or replaces the
    `[mcp_servers.coding-os]` section idempotently.

    Uses append-based text edits (no TOML parser required) so it works on
    Python 3.10 and preserves any hand-authored comments in config.toml.
    """
    if config_path and global_scope:
        raise click.ClickException("use either --config or --global, not both")

    default_path = (
        Path.home() / ".codex" / "config.toml"
        if global_scope
        else Path.cwd() / ".codex" / "config.toml"
    )
    target = Path(config_path).expanduser().resolve() if config_path else default_path

    has_cos = shutil.which("cos") is not None
    if has_cos:
        snippet = '\n[mcp_servers.coding-os]\ncommand = "cos"\nargs = ["server-start"]\n'
        command = "cos"
        args = ["server-start"]
    else:
        server_py = core_dir("thinking_os", "server.py").as_posix()
        python = sys.executable
        snippet = f'\n[mcp_servers.coding-os]\ncommand = "{python}"\nargs = ["{server_py}"]\n'
        command = python
        args = [server_py]

    if dry_run:
        click.echo(f"# Would append to {target}:")
        click.echo(snippet.rstrip())
        return

    # Locate the adapter that ships an MCP-helper script. This is the
    # codex adapter by design — discovered via registry metadata so the
    # adapter id is not hardcoded in Python code (tests/test_no_hardcoded_stacks).
    _helper_profile = next(
        (p for p in load_adapter_registry(ADAPTERS_DIR).values() if p.mcp_helper),
        None,
    )
    if _helper_profile is None:
        raise click.ClickException(
            "no adapter declares mcp_helper in adapter.yaml; cannot install MCP"
        )
    helper = _helper_profile.source_dir / _helper_profile.mcp_helper
    proc = subprocess.run(
        [sys.executable, str(helper), str(target), command, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise click.ClickException(
            proc.stderr.strip() or f"failed to configure coding-os MCP in {target}"
        )

    status = (proc.stdout or "").strip()
    if status.startswith("already configured"):
        click.echo(f"Already registered in {target} — no changes made.")
        return

    click.echo(f"OK: registered coding-os MCP in {target}")
    click.echo("Reload Codex CLI (or start a new session) to pick up the new server.")


@click.command()
@click.option("--project-dir", "-d", default=".", help="Project directory")
def health(project_dir: str) -> None:
    """Check coding-os health status."""
    project = _resolve_project_dir(project_dir)
    config = _load_config(project)

    click.echo("Coding OS Health Check")
    click.echo("=" * 40)

    # Config
    if config:
        click.echo(f"  Config:     OK ({CONFIG_FILE})")
        click.echo(f"  Agents:     {', '.join(config.get('agents', []))}")
        click.echo(f"  Templates:  {', '.join(config.get('templates', [])) or 'none'}")
    else:
        click.echo("  Config:     MISSING (run 'coding-os init')")
        return

    # State dir
    state = project / config.get("state_dir", STATE_DIR)
    if state.exists():
        click.echo(f"  State dir:  OK ({state.name}/)")
    else:
        click.echo("  State dir:  MISSING")

    # Database
    db_path = state / "coding-os.db"
    if db_path.exists():
        size_kb = db_path.stat().st_size / 1024
        click.echo(f"  Database:   OK ({size_kb:.0f} KB)")
    else:
        click.echo("  Database:   MISSING")

    # Hooks
    hooks_dir = CORE_DIR / "hooks"
    hook_count = len(list(hooks_dir.glob("*.sh"))) if hooks_dir.exists() else 0
    click.echo(f"  Core hooks: {hook_count} scripts")

    # MCP server
    server_py = CORE_DIR / "thinking_os" / "server.py"
    if server_py.exists():
        click.echo("  MCP server: OK")
    else:
        click.echo("  MCP server: MISSING")

    click.echo("")
    click.echo("Run 'coding-os init' to fix any missing components.")


@click.command()
@click.option("--project-dir", "-d", default=".", help="Project directory")
def materialize(project_dir: str) -> None:
    """Convert coding-os symlinks to real files (self-contained project)."""
    project = _resolve_project_dir(project_dir)
    materialized = 0

    for root, _dirs, files in os.walk(project):
        for name in files:
            filepath = Path(root) / name
            if filepath.is_symlink():
                target = filepath.resolve()
                if target.exists():
                    filepath.unlink()
                    shutil.copy2(target, filepath)
                    materialized += 1
                    if materialized % 50 == 0:
                        click.echo(f"  … materialized {materialized} symlinks so far", err=True)

    click.echo(f"Materialized {materialized} symlinks to real files.")
    click.echo("Project is now self-contained.")


def _is_coding_os_symlink(link: Path) -> bool:
    """True if `link` is coding-os wiring — dangling or resolving into the
    meta-repo checkout (a user's own symlink elsewhere is left alone)."""
    try:
        real = link.resolve()
    except OSError:
        return True  # broken/cyclic — it was one of ours
    if not real.exists():
        return True  # dangling: source moved/removed
    try:
        real.relative_to(CODING_OS_ROOT.resolve())
        return True
    except ValueError:
        return False


@click.command()
@click.option("--project-dir", "-d", default=".", help="Project directory")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip the confirmation prompt.")
def eject(project_dir: str, yes: bool) -> None:
    """Remove coding-os from a project, keeping your code and docs.

    Deletes coding-os symlinks, the .coding-os/ state dir and the generated
    AGENTS.md / .coding-os.yaml entrypoints, then deregisters the project. Real
    files you authored (source, docs, anything that isn't a managed symlink) are
    never touched. Re-running on an already-ejected project is a no-op.
    """
    project = _resolve_project_dir(project_dir)
    state_dir = project / STATE_DIR
    config = project / CONFIG_FILE
    coding_os_links = [
        p
        for p in (Path(root) / n for root, _d, fs in os.walk(project) for n in fs)
        if p.is_symlink() and _is_coding_os_symlink(p)
    ]
    # An adapter's root entrypoint is a generated symlink to AGENTS.md; it
    # points at a sibling, so the meta-repo filter above misses it. Only a
    # still-symlinked one is ours — a user who replaced it with a real file
    # keeps that file. Filenames come from adapter.yaml, never a literal here.
    generated_entrypoints = [config, project / "AGENTS.md"]
    generated_entrypoints += [
        link
        for name in sorted(
            {p.entrypoint_file for p in _get_adapter_registry().values() if p.entrypoint_file}
        )
        if (link := project / name).is_symlink()
    ]

    present = [f for f in generated_entrypoints if f.exists() or f.is_symlink()]
    if not coding_os_links and not state_dir.exists() and not present:
        click.echo("No coding-os install found here — nothing to eject.")
        return

    if not yes and not click.confirm(
        f"Remove coding-os from {project}? Your code and docs stay.", default=False
    ):
        click.echo("Aborted.")
        return

    for link in coding_os_links:
        link.unlink()
    removed_files = 0
    for f in present:
        f.unlink()
        removed_files += 1
    removed_state = False
    if state_dir.exists():
        shutil.rmtree(state_dir)
        removed_state = True

    # Prune adapter dirs left empty after the symlinks went; keep any that still
    # hold real (user-authored or materialized) files.
    kept_dirs: list[str] = []
    for agent_dir in sorted({p.parent for p in coding_os_links if p.parent.name.startswith(".")}):
        if agent_dir.is_dir() and not any(agent_dir.iterdir()):
            agent_dir.rmdir()
        elif agent_dir.is_dir():
            kept_dirs.append(agent_dir.name)

    from cli.registry import remove_project

    deregistered = False
    try:
        deregistered = remove_project(str(project)) is not None
    except Exception as exc:  # registry is best-effort — never block an eject
        logging.getLogger("coding_os.cli").debug("eject: deregister skipped: %s", exc)

    click.echo(f"Ejected coding-os from {project}")
    click.echo(
        f"  removed: {len(coding_os_links)} symlinks · {removed_files} config file(s)"
        + (" · .coding-os/ state" if removed_state else "")
        + (" · global-registry entry" if deregistered else "")
    )
    kept = "your source, docs, and any files you authored"
    if kept_dirs:
        kept += f" (incl. real files under {', '.join(sorted(set(kept_dirs)))})"
    click.echo(f"  kept:    {kept}")
