"""Read-only `cos graph-*` queries — thin JSON wrappers over the cos_graph_* tools."""

from __future__ import annotations

import json
from pathlib import Path

import click

from cli._graph_cli_shared import (
    _bootstrap_paths,
    _json_echo,
    _open_backend,
)


def register_query(cli: click.Group) -> None:
    """Attach this slice of the `cos graph-*` family onto `cli`."""

    @cli.command(name="graph-query")
    @click.argument("query", nargs=-1)
    @click.option("--limit", default=10, show_default=True, type=int)
    @click.option("--kinds", default="", help="Comma-separated node kinds.")
    @click.option("--max-hops", default=2, type=int)
    @click.option("--confidence-min", default=0.3, type=float)
    @click.option("--pretty", is_flag=True)
    def graph_query(query, limit, kinds, max_hops, confidence_min, pretty):
        """Hybrid search over node labels + docstrings."""
        q = " ".join(query).strip()
        if not q:
            raise click.BadParameter("query argument required")
        _, tools = _open_backend()
        result = tools.cos_graph_query(
            q,
            kinds=[k.strip() for k in kinds.split(",") if k.strip()] or None,
            limit=limit,
            max_hops=max_hops,
            confidence_min=confidence_min,
        )
        _json_echo(result, pretty=pretty)

    @cli.command(name="graph-search")
    @click.argument("query", nargs=-1)
    @click.option("--top-k", default=10, show_default=True, type=int)
    @click.option("--pretty", is_flag=True)
    def graph_search(query, top_k, pretty):
        """Hybrid semantic + lexical + centrality search over indexed code by free text."""
        q = " ".join(query).strip()
        if not q:
            raise click.BadParameter("query argument required")
        _, tools = _open_backend()
        _json_echo(tools.cos_graph_search(q, top_k=top_k), pretty=pretty)

    @cli.command(name="graph-context")
    @click.argument("uid")
    @click.option("--direction", default="both", type=click.Choice(["in", "out", "both"]))
    @click.option("--depth", default=1, type=int)
    @click.option("--include-content", is_flag=True)
    @click.option("--include-evidence", is_flag=True)
    @click.option("--pretty", is_flag=True)
    def graph_context(uid, direction, depth, include_content, include_evidence, pretty):
        """Neighbourhood around a symbol (callers + callees + refs)."""
        _, tools = _open_backend()
        _json_echo(
            tools.cos_graph_context(
                uid,
                direction=direction,
                depth=depth,
                include_content=include_content,
                include_evidence=include_evidence,
            ),
            pretty=pretty,
        )

    @cli.command(name="graph-impact")
    @click.argument("uid")
    @click.option(
        "--direction", default="downstream", type=click.Choice(["downstream", "upstream", "both"])
    )
    @click.option("--depth", default=3, type=int)
    @click.option("--confidence-min", default=0.5, type=float)
    @click.option("--pretty", is_flag=True)
    def graph_impact(uid, direction, depth, confidence_min, pretty):
        """Blast-radius of a change — risk-tiered."""
        _, tools = _open_backend()
        _json_echo(
            tools.cos_graph_impact(
                uid,
                direction=direction,
                depth=depth,
                confidence_min=confidence_min,
            ),
            pretty=pretty,
        )

    @cli.command(name="graph-references")
    @click.argument("uid")
    @click.option("--kinds", default="")
    @click.option("--limit", default=100, type=int)
    @click.option("--pretty", is_flag=True)
    def graph_references(uid, kinds, limit, pretty):
        """Inbound edges — who references this."""
        _, tools = _open_backend()
        # Empty --kinds → None so the tool auto-picks the right default edge
        # kinds PER node kind (class→constructs/inherits, fn→calls/imports).
        # A hardcoded CSV default returned 0 for class nodes (MCP parity bug).
        kset = tuple(k.strip() for k in kinds.split(",") if k.strip())
        _json_echo(
            tools.cos_graph_references(
                uid,
                kinds=kset or None,
                limit=limit,
            ),
            pretty=pretty,
        )

    @cli.command(name="graph-path")
    @click.argument("source")
    @click.argument("target")
    @click.option("--max-hops", default=5, type=int)
    @click.option("--pretty", is_flag=True)
    def graph_path(source, target, max_hops, pretty):
        """Shortest path between two nodes."""
        _, tools = _open_backend()
        _json_echo(
            tools.cos_graph_path(source, target, max_hops=max_hops),
            pretty=pretty,
        )

    @cli.command(name="graph-trace")
    @click.argument("entry_uid")
    @click.option("--max-steps", default=50, type=int)
    @click.option("--pretty", is_flag=True)
    def graph_trace(entry_uid, max_steps, pretty):
        """Forward execution walk from an entry point."""
        _, tools = _open_backend()
        _json_echo(
            tools.cos_graph_trace(entry_uid, max_steps=max_steps),
            pretty=pretty,
        )

    @cli.command(name="graph-similar")
    @click.argument("uid")
    @click.option("--top-k", default=5, type=int)
    @click.option("--confidence-min", default=0.5, type=float)
    @click.option("--pretty", is_flag=True)
    def graph_similar(uid, top_k, confidence_min, pretty):
        """Semantic-similar nodes (difflib baseline; BGE-M3 later)."""
        _, tools = _open_backend()
        _json_echo(
            tools.cos_graph_similar(uid, top_k=top_k, confidence_min=confidence_min),
            pretty=pretty,
        )

    @cli.command(name="graph-contracts")
    @click.option("--kind", default="http,mcp,grpc,event,websocket")
    @click.option("--scope", default="all")
    @click.option("--pretty", is_flag=True)
    def graph_contracts(kind, scope, pretty):
        """API surface — routes, MCP tools, gRPC, events, WS."""
        _, tools = _open_backend()
        _json_echo(
            tools.cos_graph_contracts(
                scope=scope,
                kinds=tuple(k.strip() for k in kind.split(",") if k.strip()),
            ),
            pretty=pretty,
        )

    @cli.command(name="graph-rename-plan")
    @click.argument("uid")
    @click.argument("new_name")
    @click.option("--no-strings", is_flag=True)
    @click.option("--pretty", is_flag=True)
    def graph_rename_plan(uid, new_name, no_strings, pretty):
        """Produce a rename plan — call-sites, docs, tests, strings."""
        _, tools = _open_backend()
        _json_echo(
            tools.cos_graph_rename_plan(uid, new_name, check_strings=not no_strings),
            pretty=pretty,
        )

    @cli.command(name="graph-export")
    @click.option("--format", "fmt", default="json", type=click.Choice(["json", "mermaid", "dot"]))
    @click.option("--root-uid", default=None)
    @click.option("--edge-types", default="")
    @click.option("--max-nodes", default=500, type=int)
    @click.option("--out", default=None, help="Write to file instead of stdout.")
    def graph_export(fmt, root_uid, edge_types, max_nodes, out):
        """Export a subgraph as json / mermaid / dot."""
        _, tools = _open_backend()
        envelope = tools.cos_graph_export(
            format=fmt,
            root_uid=root_uid,
            edge_types=[e.strip() for e in edge_types.split(",") if e.strip()] or None,
            max_nodes=max_nodes,
        )
        parsed = json.loads(envelope) if isinstance(envelope, str) else envelope
        if not parsed.get("ok"):
            raise click.ClickException(json.dumps(parsed))
        data = parsed["data"]
        if fmt == "json":
            payload = json.dumps(
                {"nodes": data["nodes"], "edges": data["edges"]},
                indent=2,
                default=str,
            )
        else:
            payload = data["diagram"]
        if out:
            Path(out).write_text(payload, encoding="utf-8")
            click.echo(f"[graph-export] wrote {out}")
        else:
            click.echo(payload)

    @cli.command(name="graph-stats")
    @click.option("--pretty", is_flag=True)
    def graph_stats(pretty):
        """Quick snapshot: node count, edge count, schema version."""
        backend, _ = _open_backend()
        _bootstrap_paths()
        from database import get_db_stats  # type: ignore

        stats = get_db_stats(backend._conn)
        report = {
            "schema_version": stats["schema_version"],
            "node_count": backend.count_nodes(),
            "edge_count": backend.count_edges(),
            "backend": backend.backend_id,
            "db_size_bytes": stats.get("db_size_bytes"),
        }
        _json_echo(report, pretty=pretty)

    @cli.command(name="graph-cycles")
    @click.option("--scope", default="imports", type=click.Choice(["imports", "calls"]))
    @click.option("--top", default=20, type=int)
    @click.option("--min-size", default=2, type=int)
    @click.option("--pretty", is_flag=True)
    def graph_cycles(scope, top, min_size, pretty):
        """Circular dependencies — strongly-connected components."""
        _, tools = _open_backend()
        _json_echo(
            tools.cos_graph_cycles(scope=scope, top=top, min_size=min_size),
            pretty=pretty,
        )

    @cli.command(name="graph-test-gap")
    @click.option("--kind", default="")
    @click.option("--top", default=50, type=int)
    @click.option("--pretty", is_flag=True)
    def graph_test_gap(kind, top, pretty):
        """Untested symbols — prod code with zero inbound test edge."""
        _, tools = _open_backend()
        _json_echo(tools.cos_graph_test_gap(kind=kind, top=top), pretty=pretty)

    @cli.command(name="graph-dead-code")
    @click.option("--kind", default="")
    @click.option("--top", default=50, type=int)
    @click.option("--include-tests", is_flag=True)
    @click.option("--pretty", is_flag=True)
    def graph_dead_code(kind, top, include_tests, pretty):
        """Dead-code candidates — in-repo symbols with no non-test caller."""
        _, tools = _open_backend()
        _json_echo(
            tools.cos_graph_dead_code(kind=kind, top=top, include_tests=include_tests),
            pretty=pretty,
        )

    @cli.command(name="graph-diff")
    @click.option("--base", default="HEAD~1")
    @click.option("--head", default="HEAD")
    @click.option("--pretty", is_flag=True)
    def graph_diff(base, head, pretty):
        """Blast-radius of a git range — base..head changed symbols + downstream."""
        _, tools = _open_backend()
        _json_echo(tools.cos_graph_diff(base=base, head=head), pretty=pretty)

    @cli.command(name="graph-resolve")
    @click.argument("q")
    @click.option("--kinds", default="")
    @click.option("--top", default=10, type=int)
    @click.option("--pretty", is_flag=True)
    def graph_resolve(q, kinds, top, pretty):
        """Resolve a label / path / partial to canonical uids."""
        _, tools = _open_backend()
        kset = tuple(k.strip() for k in kinds.split(",") if k.strip())
        _json_echo(
            tools.cos_graph_resolve(q, kinds=kset or None, top=top),
            pretty=pretty,
        )

    @cli.command(name="graph-centrality")
    @click.option("--metric", default="degree", type=click.Choice(["degree", "betweenness"]))
    @click.option("--top", default=20, type=int)
    @click.option("--kind", default="")
    @click.option("--pretty", is_flag=True)
    def graph_centrality(metric, top, kind, pretty):
        """Hub / chokepoint nodes — degree or betweenness centrality."""
        _, tools = _open_backend()
        _json_echo(
            tools.cos_graph_centrality(metric=metric, top=top, kind=kind or None),
            pretty=pretty,
        )

    @cli.command(name="graph-ranking")
    @click.option("--query", default="")
    @click.option("--top", default=20, type=int)
    @click.option("--kind", default="")
    @click.option("--pretty", is_flag=True)
    def graph_ranking(query, top, kind, pretty):
        """PageRank importance — optionally personalised by query."""
        _, tools = _open_backend()
        _json_echo(
            tools.cos_graph_ranking(query=query or None, top=top, kind=kind or None),
            pretty=pretty,
        )

    @cli.command(name="graph-doctor")
    @click.option("--fix", is_flag=True, help="Attempt safe repairs (delete dangling/stale).")
    @click.option("--pretty", is_flag=True)
    def graph_doctor(fix, pretty):
        """Graph health — orphans, dangling edges, duplicates, backend status."""
        _, tools = _open_backend()
        _json_echo(tools.cos_graph_doctor(fix=fix), pretty=pretty)

    @cli.command(name="graph-communities")
    @click.option("--top", default=20, show_default=True, type=int)
    @click.option("--min-size", default=2, show_default=True, type=int)
    @click.option("--pretty", is_flag=True)
    def graph_communities(top, min_size, pretty):
        """Louvain process clusters (TASK-075).

        Reads the indexed graph; computes Louvain communities over
        the call/import subgraph.  Use to seed the Search tab grouping
        or to audit how the graph clusters into named processes.
        """
        _, tools = _open_backend()
        result = tools.cos_graph_communities(top=int(top), min_size=int(min_size))
        _json_echo(result, pretty=pretty)

    @cli.command(name="graph-entrypoints")
    @click.option("--top", default=20, show_default=True, type=int)
    @click.option(
        "--kind",
        default="",
        help="Filter on entry_kind: main / cli / http / cron / test.",
    )
    @click.option("--min-score", default=0.05, show_default=True, type=float)
    @click.option("--pretty", is_flag=True)
    def graph_entrypoints(top, kind, min_score, pretty):
        """Top-N scored entry points (main / cli / http / cron / test) — TASK-081.

        Reads the indexed graph; no file re-parsing.  Use to seed
        cos_graph_trace, populate the Hub Graph tab "Start from entry
        point" panel, or sanity-check after a reindex.
        """
        _, tools = _open_backend()
        result = tools.cos_graph_entrypoints(
            top=int(top),
            kind=(kind or None),
            min_score=float(min_score),
        )
        _json_echo(result, pretty=pretty)
