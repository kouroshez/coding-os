"""graph_os CLI subcommands.

Registers the `cos graph-*` family on the root `cli` group:

    cos graph-reindex [--path DIR] [--no-docs]
    cos graph-query "<phrase>" [--limit N] [--kinds ...]
    cos graph-context <uid>
    cos graph-impact <uid> [--downstream|--upstream]
    cos graph-references <uid>
    cos graph-path <src> <dst>
    cos graph-contracts [--kind http,mcp,...]
    cos graph-rename-plan <uid> <new-name>
    cos graph-export [--format json|mermaid|dot] [--out FILE]
    cos graph-viz [--path DIR] [--out FILE] [--serve] [--port N]
    cos graph-stats
    cos graph-index-local <path>
    cos graph-index-github <url> [--auth TOKEN]
    cos graph-index-zip <archive>
    cos graph-group create|add|remove|list|status|sync|query|contracts|viz ...

Every subcommand prints JSON by default so scripts and agents can parse
consistently. `--pretty` or the absence of `--json` picks a readable
form.

All commands go through the same envelope shape as the MCP tools
(Rule 14) so agents running `cos` in a shell get the same signal they
would via MCP.
"""

from __future__ import annotations

import click

from cli._graph_cli_group import register_group
from cli._graph_cli_ingest import register_ingest
from cli._graph_cli_query import register_query
from cli._graph_cli_reindex import (  # noqa: F401 — pre-split re-export
    _is_lock_shaped,
    _parallel_dispatch,
    _report_failure_reason,
    register_reindex,
)
from cli._graph_cli_shared import (  # noqa: F401 — pre-split re-export
    _bootstrap_paths,
    _graph_reindex_print_status,
    _json_echo,
    _open_backend,
)


def register(cli: click.Group) -> None:
    """Attach every `cos graph-*` subcommand onto the parent `cli` group."""
    register_query(cli)
    register_reindex(cli)
    register_ingest(cli)
    register_group(cli)


__all__ = ["register"]
