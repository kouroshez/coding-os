"""Runtime-inspection commands: hooks-dir, hooks-log, hooks-list, server-start, session-state.

Read-only views onto the hook stream, the MCP server and the per-session state
files, plus the one command that starts the server.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

import click

from cli._cli_paths import _resolve_project_dir
from cli._init_registries import ADAPTERS_DIR, CORE_DIR, STATE_DIR
from cli._init_world import _load_config
from cli.adapter_registry import load_adapter_registry


@click.command("hooks-dir")
def hooks_dir() -> None:
    """Print the path to the core hooks directory."""
    click.echo(CORE_DIR / "hooks")


@click.command("hooks-log")
@click.option("--project-dir", "-d", default=".", help="Project directory")
@click.option("-n", "tail_count", default=50, help="Show last N lines (default 50)")
@click.option("--follow", "-f", is_flag=True, default=False, help="Follow new entries (tail -f)")
@click.option("--agent", type=str, default=None, help="Filter by agent (claude|codex|unknown)")
@click.option("--session", type=str, default=None, help="Filter by session id (substring match)")
@click.option("--task", type=str, default=None, help="Filter by task name (substring match)")
@click.option("--hook", type=str, default=None, help="Filter by hook name (substring match)")
@click.option(
    "--all",
    "--verbose",
    "show_all",
    is_flag=True,
    default=False,
    help="Show lifecycle rows (enter/ok) too; default hides them.",
)
def hooks_log(
    project_dir: str,
    tail_count: int,
    follow: bool,
    agent: str | None,
    session: str | None,
    task: str | None,
    hook: str | None,
    show_all: bool,
) -> None:
    """Show recent hook activity from .coding-os/.hooks.log.

    Hooks call `cos_log_hook` (from src/core/hooks/cos-env.sh) on fire / block /
    allow / warn. Every line carries `agent=X session=Y task=Z` identity
    fields so you can filter by any combination:

        cos hooks-log --agent claude                   # only claude runs
        cos hooks-log --session ses-20260418-143638-c769
        cos hooks-log --task governance-mcp-envelope --hook enforce-
        cos hooks-log --agent codex --follow           # live codex stream
        cos hooks-log --all                            # include enter/ok noise

    By default only decision-states (fire/block/warn/paths/reminded/full/
    debounced/skip/bypass) are shown; lifecycle rows ([enter]/[ok]) are hidden
    behind --all/--verbose. Filters are AND-ed together (case-sensitive
    substring match).
    """
    project = _resolve_project_dir(project_dir)
    config = _load_config(project) or {}
    state = project / config.get("state_dir", STATE_DIR)
    log_path = state / ".hooks.log"

    if not log_path.exists():
        click.echo(f"No hook activity yet ({log_path} does not exist).")
        click.echo(
            "Hint: hooks log on fire — if you expected events, check"
            " .claude/settings.json or .codex/hooks.json wiring."
        )
        return

    # Lifecycle actions are bookkeeping, not decisions — hide them by default
    # so `cos hooks-log` surfaces signal (fire/block/warn/...) over noise.
    lifecycle_actions = {"[enter]", "[ok]"}

    def _is_decision_state(line: str) -> bool:
        return not any(token in line for token in lifecycle_actions)

    filters: list[str] = []
    if agent:
        filters.append(f"agent={agent}")
    if session:
        filters.append(f"session={session}")
    if task:
        filters.append(f"task={task}")
    if hook:
        filters.append(f"[{hook}")

    if follow:
        tail_cmd = f"tail -f -n {tail_count} {shlex.quote(str(log_path))}"
        pipe = [tail_cmd]
        if not show_all:
            pipe.append("grep --line-buffered -vE '\\[(enter|ok)\\]'")
        pipe.extend(f"grep -F --line-buffered {shlex.quote(f)}" for f in filters)
        subprocess.run(["bash", "-c", " | ".join(pipe)])
        return

    try:
        lines = log_path.read_text(errors="replace").splitlines()
    except OSError as exc:
        click.echo(f"Could not read {log_path}: {exc}", err=True)
        return
    matched = [
        ln for ln in lines if all(f in ln for f in filters) and (show_all or _is_decision_state(ln))
    ]
    for ln in matched[-tail_count:]:
        click.echo(ln)


@click.command("hooks-list")
@click.option("--agent", type=str, default=None, help="Filter by adapter (claude|codex)")
@click.option("--category", type=str, default=None, help="Filter by category")
@click.option("--phase", type=str, default=None, help="Filter by phase")
def hooks_list(agent: str | None, category: str | None, phase: str | None) -> None:
    """List hooks registered in src/core/hooks/registry.yaml with filters.

    Reads the manifest SSOT and prints a summary. With --agent, filters to
    hooks whose events fit that adapter's declared capabilities — answers
    "what enforcement is active for Codex?" without grepping settings.
    """
    from cli.hook_renderer import list_hooks_for_agent, load_registry

    registry_path = CORE_DIR / "hooks" / "registry.yaml"
    if not registry_path.exists():
        click.echo(f"ERROR: {registry_path} not found", err=True)
        sys.exit(1)

    entries = load_registry(registry_path)
    if agent:
        entries = list_hooks_for_agent(entries, agent, ADAPTERS_DIR)
    if category:
        entries = [h for h in entries if h.category == category]
    if phase:
        entries = [h for h in entries if str(h.phase) == phase]

    if not entries:
        click.echo("No hooks match the filters.")
        return

    by_cat: dict[str, list] = {}
    for h in entries:
        by_cat.setdefault(h.category or "uncategorized", []).append(h)

    for cat in sorted(by_cat):
        click.echo(f"\n[{cat}]")
        for h in by_cat[cat]:
            events = ", ".join(
                f"{e['event']}::{e.get('matcher', '')}".rstrip(":") for e in h.events
            )
            click.echo(f"  {h.id:30s}  phase={h.phase!s:3s}  events=[{events}]")
            if h.description:
                click.echo(f"    {h.description}")
    click.echo("")


@click.command("server-start")
def server_start() -> None:
    """Start the thinking_os MCP server (wrapper used by .mcp.json).

    Projects register `cos server-start` in their .mcp.json so the MCP
    entry stays portable — coding-os location is resolved at call time by
    whichever `cos` binary is on PATH, not hardcoded per-install.

    Historically this wrapper re-entered `uv run --directory ...`, which
    dragged in `~/.cache/uv` at every MCP launch. In sandboxed runtimes
    that cache path may be unreadable, causing MCP startup to fail before
    the server process even booted. We already have a Python interpreter
    available — the one running `cos` itself — so execute `server.py`
    directly with that interpreter instead.

    We still capture the caller's cwd (the real project root the agent
    launched us from) and export it as COS_DB_PATH / COS_STATE_DIR so the
    server reads the right DB regardless of its own source location.
    """
    server_py = CORE_DIR / "thinking_os" / "server.py"
    if not server_py.exists():
        click.echo(f"ERROR: MCP server not found at {server_py}", err=True)
        sys.exit(1)

    caller_cwd = Path.cwd().resolve()
    env = os.environ.copy()
    # Only inject if the caller hasn't already set them — respects
    # explicit overrides for tests / multi-project setups.
    env.setdefault(
        "COS_DB_PATH",
        str(caller_cwd / STATE_DIR / "coding-os.db"),
    )
    env.setdefault(
        "COS_STATE_DIR",
        str(caller_cwd / STATE_DIR),
    )

    # Exec so signals / stdio pass through cleanly (MCP is stdio-based).
    python = sys.executable
    os.execvpe(
        python,
        [
            python,
            str(server_py),
        ],
        env,
    )


@click.command("session-state")
@click.option("--project-dir", "-d", default=".", help="Project directory")
def session_state(project_dir: str) -> None:
    """Show current session gate, task, and skill state."""
    import time

    from cli.board_commands import _detect_agent_runtime

    project = Path(project_dir).resolve()
    agent = os.environ.get("COS_AGENT") or _detect_agent_runtime()
    if not agent:
        adapters = sorted(load_adapter_registry(ADAPTERS_DIR).keys())
        if not adapters:
            click.echo("No adapters registered under src/adapters/.", err=True)
            sys.exit(1)
        agent = adapters[0]
    agent_dir = project / ".coding-os" / agent

    if not agent_dir.exists():
        click.echo(f"No session state at {agent_dir}")
        sys.exit(1)

    session_file = agent_dir / "session-id"
    current_session = session_file.read_text().strip() if session_file.exists() else ""

    def _read_state(path: Path, max_age: int = 7200) -> tuple[str, str]:
        if not path.exists():
            return ("none", "")
        try:
            content = path.read_text().splitlines()[0] if path.exists() else ""
        except OSError:
            return ("error", "")
        parts = content.split(" ", 1)
        file_session = parts[0] if parts else ""
        value = parts[1] if len(parts) > 1 else ""
        if current_session and file_session and file_session != current_session:
            return ("session-mismatch", value)
        age = int(time.time() - path.stat().st_mtime)
        if age > max_age:
            return (f"stale ({age // 60}min old, max {max_age // 60}min)", value)
        return ("valid", value)

    gate_status, gate_val = _read_state(agent_dir / ".thinking_os-gate")
    task_status, task_val = _read_state(agent_dir / ".task-current")
    skill_status, skill_val = _read_state(agent_dir / ".active-skill")
    zoom_status, _ = _read_state(agent_dir / ".zoom-checkpoint")
    doc_status, _ = _read_state(agent_dir / ".doc-anchor")

    click.echo(f"Session   : {current_session or '(unset)'}")
    click.echo(f"Agent     : {agent}")
    click.echo(f"Gate      : {gate_status:30s} {gate_val}")
    click.echo(f"Zoom      : {zoom_status}")
    click.echo(f"Task      : {task_status:30s} {task_val}")
    click.echo(f"Skill     : {skill_status:30s} {skill_val}")
    click.echo(f"DocAnchor : {doc_status}")

    if "stale" in gate_status or gate_status == "none":
        click.echo("")
        click.echo("Gate not valid — next Write/Edit on .py/.ts/.tsx will BLOCK")
        click.echo(f'   Re-record: bash "{agent_dir}/hooks/write-state.sh" \\')
        click.echo('              .thinking_os-gate "CLEAR 1"')
        click.echo("   (bare basename auto-routes to $COS_PANEL_DIR via cos_state_path)")
