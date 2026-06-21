from __future__ import annotations

import json

import click


def _query_logs(level: str, scope: str, since: str, search: str, limit: int) -> dict:
    # Deferred + dual-path imports: bare names resolve under the installed CLI
    # runtime, the `core.*` prefix under pytest. Keeps startup cheap and the
    # command tolerant of a partial install.
    try:
        from database import init_db
        from tools.logs import log_query
    except ImportError:
        from core.thinking_os.database import init_db
        from core.thinking_os.tools.logs import log_query

    conn = init_db()
    return log_query(
        conn,
        level=level or None,
        scope=scope or None,
        since=since or None,
        search=search or None,
        limit=limit,
    )


def _emit(result: dict, as_json: bool, level_label: str) -> None:
    if as_json:
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
        return
    rows = result["rows"]
    if not rows:
        click.echo(f"No log events match (total in store: {result['total']}).", err=True)
        return
    try:
        from logging_os.render import render
    except ImportError:
        from core.logging_os.render import render

    for row in rows:
        kv: dict = {}
        if row.get("kv"):
            try:
                kv = json.loads(row["kv"])
            except (ValueError, TypeError):
                kv = {}
        if row.get("fingerprint"):
            kv["fp"] = row["fingerprint"]
        click.echo(
            render(
                "short",
                {
                    "ts": row["ts"],
                    "lvl": row["lvl"],
                    "scope": row["scope"],
                    "msg": row["msg"],
                    "kv": kv,
                },
            )
        )
    # Narration → stderr; rows (the result) → stdout.
    click.echo(
        f"-- {result['count']} of {result['total']} shown (level>={level_label}) --", err=True
    )


@click.command(name="logs")
@click.option("--level", default="warn", help="Severity floor: debug|info|ok|warn|error|fatal.")
@click.option("--scope", default="", help="Scope glob, e.g. 'cli.*' or 'hook.branch_guard'.")
@click.option("--since", default="", help="ISO8601 lower bound, e.g. 2026-06-05T00:00:00Z.")
@click.option("--search", default="", help="Substring match on the message.")
@click.option("--limit", default=50, type=int, help="Max rows (1..2000).")
@click.option("--json", "as_json", is_flag=True, help="Emit the raw JSON envelope.")
def logs_cmd(level: str, scope: str, since: str, search: str, limit: int, as_json: bool) -> None:
    """Show recent durable log events (WARN+) captured by the observability eye."""
    _emit(_query_logs(level, scope, since, search, limit), as_json, level)


@click.command(name="errors")
@click.option("--since", default="", help="ISO8601 lower bound, e.g. 2026-06-05T00:00:00Z.")
@click.option("--scope", default="", help="Scope glob, e.g. 'cli.*'.")
@click.option("--limit", default=50, type=int, help="Max rows (1..2000).")
@click.option("--json", "as_json", is_flag=True, help="Emit the raw JSON envelope.")
def errors_cmd(since: str, scope: str, limit: int, as_json: bool) -> None:
    """Show recent ERROR+ events — the eye's 'what is broken now'."""
    _emit(_query_logs("error", scope, since, "", limit), as_json, "error")
