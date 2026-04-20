"""cos board-* CLI commands (Phase L.6).

16 commands:
    cos board [--web] [--port N] [--swimlane] [--kind] [--epic] [--priority]
    cos task-create
    cos task-move
    cos task-start / task-done / task-block / task-cancel
    cos task-pick
    cos task-archive
    cos daily / retro
    cos task-show / task-log / task-history / wip
    cos task-validate
    cos board-config --init

Thin click wrappers over core.board_os.{mcp_tools,workflow,parser,sync}.
All commands use the project's SQLite DB (.coding-os/thinking-os.db)
unless COS_DB_PATH overrides.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import click

# Bootstrap so imports work whether invoked via `cos` entry-point or bare python.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _project_root() -> Path:
    return Path(os.environ.get("COS_PROJECT_ROOT") or os.getcwd()).resolve()


def _db_conn() -> sqlite3.Connection:
    root = _project_root()
    db_path = os.environ.get(
        "COS_DB_PATH", str(root / ".coding-os" / "thinking-os.db"),
    )
    if not Path(db_path).exists():
        click.echo(f"ERROR: DB not found at {db_path}. Run `cos setup` first.", err=True)
        sys.exit(1)
    return sqlite3.connect(db_path)


def _parse_envelope(envelope: str) -> dict:
    return json.loads(envelope)


def _print_envelope(envelope: str, *, format: str = "text") -> int:
    data = _parse_envelope(envelope)
    if format == "json":
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        return 0 if data.get("ok") else 1
    if not data.get("ok"):
        click.echo(f"ERROR [{data['error']['category']}]: {data['error']['message']}", err=True)
        return 1
    click.echo(json.dumps(data["data"], indent=2, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# cos board
# ---------------------------------------------------------------------------


@click.command("board", help="Show Scrumban board (ASCII or --web)")
@click.option("--web", is_flag=True, default=False, help="Open board in browser")
@click.option("--port", type=int, default=9000)
@click.option("--host", default="127.0.0.1")
@click.option("--bind", default=None, help="Bind address (overrides --host)")
@click.option("--swimlane", default=None)
@click.option("--kind", default=None)
@click.option("--epic", default=None)
@click.option("--priority", default=None, help="Comma-separated (e.g. P0,P1)")
@click.option("--format", type=click.Choice(["text", "json"]), default="text")
def board_cmd(web, port, host, bind, swimlane, kind, epic, priority, format):
    from core.board_os import mcp_tools
    if web:
        from core.board_os.viewer.server import serve_board
        serve_board(
            host=(bind or host), port=port, project_root=_project_root(),
        )
        return
    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_board(
            conn,
            swimlane=swimlane, kind=kind, epic=epic,
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
                    "bug": "🔴", "feature": "🟡", "chore": "🟢", "spike": "🔵",
                    "docs": "🟣", "refactor": "🟦", "test": "🟧", "security": "🟠",
                }.get(card["kind"], "⚪")
                click.echo(
                    f"      {badge} {card['id']} [{card['priority']}] {card['title']}"
                )
        click.echo()


# ---------------------------------------------------------------------------
# task-create / task-move / task-start / task-done / task-block / task-cancel
# ---------------------------------------------------------------------------


@click.command("task-create", help="Create a new Scrumban task (lean template).")
@click.option("--title", required=True)
@click.option("--swimlane", required=True)
@click.option("--kind", required=True,
              type=click.Choice(["feature", "bug", "chore", "spike", "docs",
                                 "refactor", "test", "security"]))
@click.option("--priority", default="P2", type=click.Choice(["P0", "P1", "P2", "P3"]))
@click.option("--appetite", default="1d")
@click.option("--epic", default=None)
@click.option("--labels", default="", help="Comma-separated free tags")
@click.option("--outcome", default=None)
@click.option("--depends-on", default="", help="Comma-separated TASK-IDs")
def task_create_cmd(title, swimlane, kind, priority, appetite, epic, labels,
                    outcome, depends_on):
    from core.board_os import mcp_tools
    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_create(
            conn,
            title=title, swimlane=swimlane, kind=kind,
            priority=priority, appetite=appetite,
            epic=epic,
            labels=[l.strip() for l in labels.split(",") if l.strip()],
            outcome=outcome,
            depends_on=[d.strip() for d in depends_on.split(",") if d.strip()],
        )
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


@click.command("task-move")
@click.argument("task_id")
@click.option("--to", required=True)
@click.option("--reason", default=None)
@click.option("--force", is_flag=True, default=False, help="Bypass WIP cap")
def task_move_cmd(task_id, to, reason, force):
    from core.board_os import mcp_tools
    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_move(
            conn, task_id=task_id, to=to, reason=reason, bypass_wip=force,
        )
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


def _simple_move(task_id: str, to: str, *, reason: str | None = None,
                 force: bool = False):
    from core.board_os import mcp_tools
    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_move(
            conn, task_id=task_id, to=to, reason=reason, bypass_wip=force,
        )
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


@click.command("task-start")
@click.argument("task_id")
@click.option("--force", is_flag=True, default=False)
def task_start_cmd(task_id, force):
    _simple_move(task_id, "in_progress", force=force)


@click.command("task-done")
@click.argument("task_id")
def task_done_cmd(task_id):
    _simple_move(task_id, "complete")


@click.command("task-block")
@click.argument("task_id")
@click.option("--reason", required=True)
def task_block_cmd(task_id, reason):
    _simple_move(task_id, "blocked", reason=reason)


@click.command("task-cancel")
@click.argument("task_id")
@click.option("--reason", default=None)
def task_cancel_cmd(task_id, reason):
    _simple_move(task_id, "icebox", reason=f"cancelled: {reason or 'no reason given'}")


# ---------------------------------------------------------------------------
# task-pick / daily / retro / wip
# ---------------------------------------------------------------------------


@click.command("task-pick", help="Print top candidate tasks to work on next.")
@click.option("--swimlane", default=None)
@click.option("--priority-min", default="P2", type=click.Choice(["P0", "P1", "P2", "P3"]))
@click.option("--max-candidates", default=3, type=int)
def task_pick_cmd(swimlane, priority_min, max_candidates):
    from core.board_os import mcp_tools
    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_pick(
            conn, swimlane=swimlane, priority_min=priority_min,
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
        click.echo(f"  {i}. {c['id']} [{c['priority']}] {c['title']}  ({c['swimlane']}/{c['kind']})")
    click.echo()


@click.command("daily", help="Morning standup — summary of last 24h.")
@click.option("--since", default="24h")
def daily_cmd(since):
    from core.board_os import mcp_tools
    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_daily(conn, since=since)
    finally:
        conn.close()
    # Touch daily marker for remind-daily.sh.
    # $COS_AGENT_DIR is agent-scoped (.coding-os/<agent>/); default to generic
    # .coding-os/ to avoid hardcoding a specific adapter here.
    marker = Path(
        os.environ.get("COS_AGENT_DIR", str(_project_root() / ".coding-os")),
    ) / ".daily-last-run"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("", encoding="utf-8")
    sys.exit(_print_envelope(envelope))


@click.command("retro", help="Weekly retrospective — throughput + cycle time.")
@click.option("--since", default="7d")
def retro_cmd(since):
    from core.board_os import mcp_tools
    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_retro(conn, since=since)
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


@click.command("wip", help="Current WIP counts vs. caps.")
def wip_cmd():
    from core.board_os import mcp_tools
    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_wip_check(conn)
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


# ---------------------------------------------------------------------------
# task-show / task-log / task-history
# ---------------------------------------------------------------------------


@click.command("task-show", help="Show a task's full content + frontmatter.")
@click.argument("task_id")
def task_show_cmd(task_id):
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
    click.echo(f"  status={row[2]} swimlane={row[3]} kind={row[4]} priority={row[5]} appetite={row[6]}")
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


# ---------------------------------------------------------------------------
# task-validate / board-config
# ---------------------------------------------------------------------------


@click.command("task-validate", help="Lint all docs/tasks/*.md files.")
def task_validate_cmd():
    from core.board_os.parser import parse_task
    root = _project_root()
    tasks_dir = root / "docs" / "tasks"
    if not tasks_dir.exists():
        click.echo(f"  (no {tasks_dir})")
        return
    errors = 0
    warnings = 0
    for p in sorted(tasks_dir.glob("TASK-*.md")):
        content = p.read_text(encoding="utf-8")
        parsed = parse_task(content, path=p)
        if parsed is None:
            click.echo(f"  ✗ {p.name}: unparseable", err=True)
            errors += 1
            continue
        if parsed.parse_warnings:
            for w in parsed.parse_warnings:
                click.echo(f"  ⚠ {p.name}: {w}")
                warnings += 1
        else:
            click.echo(f"  ✓ {p.name}")
    click.echo(f"\n  Total: {errors} errors, {warnings} warnings")
    sys.exit(1 if errors > 0 else 0)


def _discover_stacks() -> list[str]:
    """Data-driven — read templates/ to find available stack ids."""
    templates_dir = _REPO_ROOT / "templates"
    if not templates_dir.exists():
        return []
    return sorted(
        p.name for p in templates_dir.iterdir()
        if p.is_dir() and (p / "scaffold").exists()
    )


@click.command("board-config", help="Scaffold or inspect scrumban-config.yaml")
@click.option("--init", is_flag=True, default=False)
@click.option("--stack", default="_base")
def board_config_cmd(init, stack):
    valid_stacks = _discover_stacks() or ["_base"]
    if stack not in valid_stacks:
        click.echo(
            f"ERROR: stack {stack!r} not in {valid_stacks}", err=True,
        )
        sys.exit(1)
    root = _project_root()
    config_path = root / ".coding-os" / "scrumban-config.yaml"
    if init:
        if config_path.exists():
            click.echo(f"ERROR: {config_path} already exists", err=True)
            sys.exit(1)
        source = (
            _REPO_ROOT / "templates" / stack / "scaffold" / ".coding-os"
            / "scrumban-config.yaml"
        )
        if not source.exists():
            source = (
                _REPO_ROOT / "templates" / "_base" / "scaffold" / ".coding-os"
                / "scrumban-config.yaml"
            )
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        click.echo(f"  Created {config_path} (from {stack})")
    else:
        if not config_path.exists():
            click.echo(f"ERROR: {config_path} not found; run --init", err=True)
            sys.exit(1)
        click.echo(config_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Commands bundle — register via cli.add_command(each)
# ---------------------------------------------------------------------------


BOARD_COMMANDS = [
    board_cmd,
    task_create_cmd, task_move_cmd,
    task_start_cmd, task_done_cmd, task_block_cmd, task_cancel_cmd,
    task_pick_cmd, daily_cmd, retro_cmd, wip_cmd,
    task_show_cmd, task_log_cmd, task_history_cmd,
    task_validate_cmd, board_config_cmd,
]
