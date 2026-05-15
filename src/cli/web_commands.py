"""cli.web_commands — `cos web` command for launching the unified web server."""

from __future__ import annotations

import sys

import click


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
    """Start the Coding OS unified web server (S4 backbone)."""
    try:
        from web.server import run_server  # type: ignore
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
