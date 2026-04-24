"""cli.web_commands — `cos web` command for launching the unified web server.

PURPOSE: CLI entry-point that starts the FastAPI/uvicorn server on port 9188
         (default) with optional --reload for development and --host override.
INPUT:   CLI flags: --port INT, --host STR, --reload (flag), --log-level STR.
OUTPUT:  none (starts uvicorn, blocks until killed).
DEPENDENCIES: click, core.web.server.run_server.
NOTES:  Follows the same lazy-import pattern as graph_commands.py.
        Registered in cli/main.py at the end alongside graph_commands.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

# Ensure repo root is on sys.path so `from core.web...` works.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@click.command(name="web")
@click.option("--port", default=9188, show_default=True, type=int,
              help="TCP port to listen on. Default is 9188 "
                   "(stable, user-facing URL; IANA-unassigned).")
@click.option("--host", default="127.0.0.1", show_default=True,
              help="Host/interface to bind.")
@click.option("--reload", is_flag=True, default=False,
              help="Enable auto-reload for development (watchfiles).")
@click.option("--log-level", default="info", show_default=True,
              type=click.Choice(["debug", "info", "warning", "error", "critical"],
                                case_sensitive=False),
              help="Uvicorn log level.")
def web_cmd(port: int, host: str, reload: bool, log_level: str) -> None:
    """Start the Coding OS unified web server (S4 backbone).

    PURPOSE: Launch FastAPI/uvicorn serving graph, board, cognition, and
             search APIs at /api/*, plus SSE stream and Prometheus metrics.
    INPUT:   --port, --host, --reload, --log-level CLI flags.
    OUTPUT:  Running HTTP server (blocks until SIGTERM/SIGINT).
    DEPENDENCIES: core.web.server.run_server, uvicorn.
    NOTES:  The default port 9188 is the stable public URL for the
            coding-os web SPA (bookmarkable across sessions).
    """
    try:
        from core.web.server import run_server  # type: ignore
    except ImportError as exc:
        click.echo(
            f"ERROR: could not import core.web.server: {exc}\n"
            "Make sure you have installed the web extras: uv sync",
            err=True,
        )
        sys.exit(1)

    click.echo(f"Starting Coding OS web server on http://{host}:{port} ...")
    if reload:
        click.echo("  Dev mode: auto-reload enabled.")

    run_server(host=host, port=port, reload=reload, log_level=log_level.lower())
