"""Shared plumbing for the `cos graph-*` family: path bootstrap, backend handle, output."""

from __future__ import annotations

import json
import sys
from typing import Any

import click

# ---------------------------------------------------------------------------
# Lazy bootstrap — push core/ + src/core/thinking_os onto sys.path.
# ---------------------------------------------------------------------------


def _bootstrap_paths() -> None:
    from cli._resources import core_dir as _core_dir

    core_path = _core_dir()
    tos_dir = core_path / "thinking_os"
    for candidate in (core_path, tos_dir):
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


def _json_echo(payload: Any, *, pretty: bool = False) -> None:
    if isinstance(payload, str):
        # Already a JSON envelope from a `cos_graph_*` tool.
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            click.echo(payload)
            return
    if pretty:
        click.echo(json.dumps(payload, indent=2, default=str))
    else:
        click.echo(json.dumps(payload, default=str))


def _open_backend():
    _bootstrap_paths()
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend  # type: ignore
    from graph_os.tools import graph as graph_tools  # type: ignore

    conn = init_db()
    backend = SqliteBackend(conn=conn)
    graph_tools._BACKEND_SINGLETON = backend
    return backend, graph_tools


def _graph_reindex_print_status() -> None:
    """V1 ``--status``: print top 50 most-recently-indexed file_index_state rows."""
    from datetime import datetime, timezone

    _bootstrap_paths()
    try:
        import database  # type: ignore
    except ImportError as exc:
        raise click.ClickException(f"thinking_os db import failed: {exc}") from exc
    conn = database.init_db()
    try:
        if not database.has_file_index_state_table(conn):
            click.echo(
                "[graph-reindex] file_index_state table missing (migration v17 not applied)."
            )
            return
        rows = conn.execute(
            "SELECT file_path, content_hash, extractor_chain, "
            "last_indexed_at, last_error FROM file_index_state "
            "ORDER BY last_indexed_at DESC LIMIT 50"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        click.echo("[graph-reindex] file_index_state is empty.")
        return

    click.echo(f"{'file_path':<60}  {'hash':<12}  {'indexed_at':<20}  status")
    click.echo("-" * 110)
    for file_path, chash, chain, ts, err in rows:
        when = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        status = "error" if err else "ok"
        chain_hint = chain[:20] + ("…" if len(chain) > 20 else "")
        display = f"{file_path} [{chain_hint}]"
        if len(display) > 60:
            display = display[:57] + "..."
        click.echo(f"{display:<60}  {chash[:12]:<12}  {when:<20}  {status}")
