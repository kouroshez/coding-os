"""Read-only board views: board, task-pick, daily, retro, wip, task-show, task-log, task-history."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click

from cli._board_cli_shared import (
    _db_conn,
    _parse_envelope,
    _print_envelope,
    _project_root,
)

# ---------------------------------------------------------------------------
# cos board
# ---------------------------------------------------------------------------


def _launch_board_in_spa(*, host: str, port: int) -> None:
    """Open the unified SPA Board page; auto-start `cos web` if needed."""
    import urllib.error
    import urllib.request
    import webbrowser

    url = f"http://{host}:{port}/board"
    health_url = f"http://{host}:{port}/health"

    def _server_up() -> bool:
        try:
            with urllib.request.urlopen(health_url, timeout=0.5) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    if _server_up():
        click.echo(f"Opening {url} (web server already running).")
        webbrowser.open(url)
        return

    click.echo(f"Starting Coding OS web server on {host}:{port} ... (Ctrl-C to stop)")
    click.echo(f"Once it is up, open {url} in your browser.")
    try:
        from web.server import run_server
    except ImportError as exc:
        click.echo(
            f"ERROR: could not import core.web.server: {exc}\nInstall web extras: uv sync",
            err=True,
        )
        sys.exit(1)
    run_server(host=host, port=port)


@click.command("board", help="Show Scrumban board (ASCII or --web)")
@click.option(
    "--web",
    is_flag=True,
    default=False,
    help="Open board in browser (redirects to unified SPA at /board)",
)
@click.option(
    "--port", type=int, default=9188, help="Port for the unified web server when --web is used."
)
@click.option("--host", default="127.0.0.1")
@click.option("--bind", default=None, help="Bind address (overrides --host)")
@click.option("--swimlane", default=None)
@click.option("--kind", default=None)
@click.option("--epic", default=None)
@click.option("--priority", default=None, help="Comma-separated (e.g. P0,P1)")
@click.option("--format", type=click.Choice(["text", "json"]), default="text")
def board_cmd(web, port, host, bind, swimlane, kind, epic, priority, format):
    from board_os import mcp_tools

    if web:
        _launch_board_in_spa(host=(bind or host), port=port)
        return
    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_board(
            conn,
            swimlane=swimlane,
            kind=kind,
            epic=epic,
        )
    finally:
        conn.close()

    # Client-side priority filter (MCP tool doesn't expose it yet).
    if priority:
        allowed = {p.strip().upper() for p in priority.split(",") if p.strip()}
        parsed = _parse_envelope(envelope)
        if parsed.get("ok"):
            cards = parsed["data"].get("cards", [])
            parsed["data"]["cards"] = [c for c in cards if c.get("priority") in allowed]
            parsed["data"]["count"] = len(parsed["data"]["cards"])
            envelope = json.dumps(parsed)

    if format == "text":
        _render_board_ascii(envelope)
    else:
        click.echo(envelope)


def _render_board_ascii(envelope: str) -> None:
    env = _parse_envelope(envelope)
    if not env.get("ok"):
        click.echo(f"ERROR: {env['error']['message']}", err=True)
        return
    data = env["data"]
    grouped = data.get("grouped", {})
    wip = data.get("wip") or {}

    click.echo("\n  Scrumban Board")
    click.echo("  " + "─" * 60)
    if wip.get("counts"):
        parts = []
        for col in ("in_progress", "testing", "emergency"):
            n = wip["counts"].get(col, 0)
            c = wip["caps"].get(col, "?")
            mark = "🔴" if col in wip.get("violations", []) else "·"
            parts.append(f"{col} {n}/{c} {mark}")
        click.echo("  WIP: " + " | ".join(parts))
    click.echo()

    statuses = ["icebox", "ready", "emergency", "in_progress", "testing", "blocked"]
    for lane in sorted(grouped.keys()):
        click.echo(f"  ── {lane} ──")
        for status in statuses:
            cards = grouped[lane].get(status, [])
            if not cards:
                continue
            click.echo(f"    [{status}]")
            for card in cards:
                badge = {
                    "bug": "🔴",
                    "feature": "🟡",
                    "chore": "🟢",
                    "spike": "🔵",
                    "docs": "🟣",
                    "refactor": "🟦",
                    "test": "🟧",
                    "security": "🟠",
                }.get(card["kind"], "⚪")
                # READY overlay: icebox cards carrying the "ready" label are
                # pickup candidates (see board_os.config::READY_LABEL).  We
                # surface this as a "✓READY" prefix so the CLI matches the
                # green pill rendered by the web Board.
                labels = card.get("labels") or []
                ready_prefix = " ✓READY " if status == "icebox" and "ready" in labels else ""
                click.echo(
                    f"      {badge}{ready_prefix} {card['id']} [{card['priority']}] {card['title']}"
                )
        click.echo()


# ---------------------------------------------------------------------------
# task-pick / daily / retro / wip
# ---------------------------------------------------------------------------


@click.command("task-pick", help="Print top candidate tasks to work on next.")
@click.option("--swimlane", default=None)
@click.option("--priority-min", default="P2", type=click.Choice(["P0", "P1", "P2", "P3"]))
@click.option("--max-candidates", default=3, type=int)
def task_pick_cmd(swimlane, priority_min, max_candidates):
    from board_os import mcp_tools

    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_pick(
            conn,
            swimlane=swimlane,
            priority_min=priority_min,
            max_candidates=max_candidates,
        )
    finally:
        conn.close()
    env = _parse_envelope(envelope)
    if not env["ok"]:
        click.echo(f"ERROR: {env['error']['message']}", err=True)
        sys.exit(1)
    cands = env["data"]["candidates"]
    click.echo("\n  Top candidates:")
    for i, c in enumerate(cands, 1):
        click.echo(
            f"  {i}. {c['id']} [{c['priority']}] {c['title']}  ({c['swimlane']}/{c['kind']})"
        )
    click.echo()


@click.command("daily", help="Morning standup — summary of last 24h.")
@click.option("--since", default="24h")
def daily_cmd(since):
    from board_os import mcp_tools

    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_daily(conn, since=since)
    finally:
        conn.close()
    # Touch daily marker for remind-daily.sh.
    # $COS_AGENT_DIR is agent-scoped (.coding-os/<agent>/); default to generic
    # .coding-os/ to avoid hardcoding a specific adapter here.
    marker = (
        Path(
            os.environ.get("COS_AGENT_DIR", str(_project_root() / ".coding-os")),
        )
        / ".daily-last-run"
    )
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("", encoding="utf-8")
    sys.exit(_print_envelope(envelope))


@click.command("retro", help="Weekly retrospective — throughput + cycle time.")
@click.option("--since", default="7d")
def retro_cmd(since):
    from board_os import mcp_tools

    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_retro(conn, since=since)
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


@click.command("wip", help="Current WIP counts vs. caps.")
def wip_cmd():
    from board_os import mcp_tools

    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_wip_check(conn)
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


# ---------------------------------------------------------------------------
# task-show / task-log / task-history
# ---------------------------------------------------------------------------


@click.command(
    "task-show",
    help="Show a task's full content + frontmatter. Without TASK_ID, falls back to the current session task.",
)
@click.argument("task_id", required=False)
def task_show_cmd(task_id):
    if not task_id:
        agent_dir = os.environ.get("COS_AGENT_DIR")
        if agent_dir:
            current_file = Path(agent_dir) / ".task-current"
            if current_file.exists():
                # write-state.sh stores "<session-id> <value>" on one line.
                # Split off the session prefix and pull the first TASK-NNN
                # token out of the remainder (handles slugged values like
                # "TASK-NNN-some-slug").
                content = current_file.read_text(encoding="utf-8").strip()
                tokens = content.split()
                value = " ".join(tokens[1:]) if len(tokens) >= 2 else content
                import re as _re

                match = _re.search(r"TASK-(?:[A-Z][A-Z0-9]*-)?\d+", value, _re.IGNORECASE)
                if match:
                    task_id = match.group(0).upper()
        if not task_id:
            click.echo(
                "ERROR: no TASK_ID and no active task in $COS_PANEL_DIR/.task-current.\n"
                "  Hint: cos task-start TASK-NNN  (or pass TASK-NNN explicitly).",
                err=True,
            )
            sys.exit(1)
    conn = _db_conn()
    try:
        row = conn.execute(
            "SELECT task_id, title, status, swimlane, kind, priority, "
            "appetite, file_path FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        click.echo(f"ERROR: {task_id} not found", err=True)
        sys.exit(1)
    click.echo(f"  {row[0]}: {row[1]}")
    click.echo(
        f"  status={row[2]} swimlane={row[3]} kind={row[4]} priority={row[5]} appetite={row[6]}"
    )
    click.echo(f"  file: {row[7]}")
    if row[7]:
        full_path = _project_root() / row[7]
        if full_path.exists():
            click.echo("\n" + full_path.read_text(encoding="utf-8"))


@click.command("task-log", help="Show a task's Work Log.")
@click.argument("task_id")
@click.option("--full", is_flag=True, default=False)
def task_log_cmd(task_id, full):
    conn = _db_conn()
    try:
        row = conn.execute(
            "SELECT file_path, work_log_last_5 FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        click.echo(f"ERROR: {task_id} not found", err=True)
        sys.exit(1)
    if full and row[0]:
        full_path = _project_root() / row[0]
        if full_path.exists():
            content = full_path.read_text(encoding="utf-8")
            idx = content.find("## Work Log")
            if idx != -1:
                click.echo(content[idx:])
                return
    last_5 = json.loads(row[1] or "[]")
    for line in last_5:
        click.echo("  " + line)


@click.command("task-history", help="Show task status transitions.")
@click.argument("task_id")
def task_history_cmd(task_id):
    conn = _db_conn()
    try:
        rows = conn.execute(
            "SELECT old_status, new_status, agent_session, reason, transitioned_at "
            "FROM task_status_history WHERE task_id = ? "
            "ORDER BY transitioned_at",
            (task_id,),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        click.echo(f"  (no transitions for {task_id})")
        return
    click.echo(f"\n  Transitions for {task_id}:")
    import time

    for r in rows:
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(r[4]))
        click.echo(f"  {ts}  {r[0]:>12} → {r[1]:<12}  {r[3] or ''}")
