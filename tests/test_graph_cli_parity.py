"""CLI↔MCP parity for the graph surface.

Every ``cos_graph_*`` MCP tool must have a ``cos graph-*`` CLI mirror and
vice-versa (modulo a small build-only allowlist). Guards the bug class
found during the graph-os audit: nine MCP tools (references default,
cycles, test_gap, dead_code, diff, centrality, ranking, resolve, doctor)
shipped without a CLI command, so the two surfaces silently diverged and
`cos graph-cycles` 404'd while `cos_graph_cycles` worked.
"""

from __future__ import annotations

import graph_os.tools.graph as graph_tools
from cli.main import cli

# CLI-only commands: build / ingest / viz surface with no MCP tool behind them.
_CLI_ONLY = {
    "graph-reindex",
    "graph-viz",
    "graph-stats",
    "graph-group",
    "graph-index-github",
    "graph-index-local",
    "graph-index-zip",
}


def _mcp_tool_names() -> set[str]:
    return {
        n
        for n in dir(graph_tools)
        if n.startswith("cos_graph_") and callable(getattr(graph_tools, n))
    }


def _cli_name_for(tool: str) -> str:
    # cos_graph_test_gap -> graph-test-gap
    return "graph-" + tool[len("cos_graph_") :].replace("_", "-")


def _graph_cli_commands() -> set[str]:
    return {c for c in cli.commands if c.startswith("graph-")}


def test_every_mcp_graph_tool_has_cli_command() -> None:
    cli_cmds = _graph_cli_commands()
    missing = sorted(
        _cli_name_for(t) for t in _mcp_tool_names() if _cli_name_for(t) not in cli_cmds
    )
    assert not missing, f"MCP graph tools missing a `cos {{cmd}}` CLI mirror: {missing}"


def test_no_orphan_graph_cli_command() -> None:
    mirrors = {_cli_name_for(t) for t in _mcp_tool_names()}
    orphans = sorted(_graph_cli_commands() - mirrors - _CLI_ONLY)
    assert not orphans, (
        f"graph CLI commands with neither an MCP tool nor a build-only allowlist entry: {orphans}"
    )
