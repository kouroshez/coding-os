"""cos_graph_* structural-analysis tools (contracts, centrality, cycles, doctor)."""

from __future__ import annotations

from _server_runtime import (
    _GRAPH_TOOLS_AVAILABLE,
    _csv,
    _graph_tools,
    mcp,
    register_unavailable_stubs,
)
from tools._shared import safe_tool

if _GRAPH_TOOLS_AVAILABLE:

    @mcp.tool(
        name="cos_graph_contracts",
        annotations={
            "title": "Graph API Contracts",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_contracts_tool(
        scope: str = "all",
        kinds: str = "http,mcp,grpc,event,websocket",
        include_test_sources: bool = False,
    ) -> str:
        """Enumerate every handler declared in the graph (HTTP / MCP / gRPC / events / WS)."""
        return _graph_tools.cos_graph_contracts(
            scope=str(scope),
            kinds=tuple(_csv(kinds) or ("http", "mcp", "grpc", "event", "websocket")),
            include_test_sources=bool(include_test_sources),
        )

    @mcp.tool(
        name="cos_graph_entrypoints",
        annotations={
            "title": "Graph Entry Points (Scored)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_entrypoints_tool(
        top: int = 20,
        kind: str = "",
        min_score: float = 0.05,
        diversify: bool = True,
    ) -> str:
        """Top-N scored entry points (main / cli / http / cron / test) — TASK-081."""
        return _graph_tools.cos_graph_entrypoints(
            top=int(top),
            kind=(kind or None),
            min_score=float(min_score),
            diversify=bool(diversify),
        )

    @mcp.tool(
        name="cos_graph_communities",
        annotations={
            "title": "Graph Communities / Processes (Louvain)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_communities_tool(
        top: int = 50,
        min_size: int = 2,
        max_members: int = 10,
    ) -> str:
        """Louvain process clusters — response key is `processes` (not `communities`)."""
        return _graph_tools.cos_graph_communities(
            top=int(top),
            min_size=int(min_size),
            max_members=int(max_members),
        )

    @mcp.tool(
        name="cos_graph_resolve",
        annotations={
            "title": "Graph UID Resolver (NL → canonical uid)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_resolve_tool(
        q: str,
        kinds: str = "",
        top: int = 10,
    ) -> str:
        """Resolve a natural-language label, path, or partial uid to canonical uids.

        Use this BEFORE other cos_graph_* tools when you don't know the exact uid.
        Tries: direct uid → path/qualname → FTS5 full-text → LIKE fallback.

        UID scheme:
          code:file:<path> · code:function:<path>::<name> · code:class:<path>::<name>
          code:method:<path>::<class>.<name> · code:module:<dotted>
          doc:file:<path> · doc:heading:<path>#<slug>:<level> · folder:<path>

        Args:
            q: Natural language ("the dispatcher function"), label ("ClaudeSDKDispatcher"),
               path ("adapters/claude/sdk_dispatcher.py"), or qualname ("Class.method").
            kinds: Comma-separated kind filter (e.g. "function,method,class"). Empty = all.
            top: Max results (default 10).

        Returns:
            JSON envelope with `results` (ranked list of {uid, kind, label, …}) and
            `strategy` (which resolution path matched).
        """
        return _graph_tools.cos_graph_resolve(
            q,
            kinds=_csv(kinds) or None,
            top=int(top),
        )

    @mcp.tool(
        name="cos_graph_centrality",
        annotations={
            "title": "Graph Centrality (degree / betweenness)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_centrality_tool(
        metric: str = "degree",
        top: int = 20,
        kind: str = "",
    ) -> str:
        """Hub detection — surface high-degree (or high-betweenness) nodes.

        Use to identify chokepoints / refactor priorities / nodes that demand
        extra review.

        Args:
            metric: "degree" (cheap, default) or "betweenness" (expensive).
            top: Max nodes returned (default 20).
            kind: Optional kind filter (e.g. "function", "class"). Empty = all.

        Returns:
            JSON envelope with `nodes` ranked by centrality score.
        """
        return _graph_tools.cos_graph_centrality(
            metric=metric,
            top=int(top),
            kind=kind or None,
        )

    @mcp.tool(
        name="cos_graph_ranking",
        annotations={
            "title": "Graph PageRank (importance / personalised)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_ranking_tool(
        query: str = "",
        top: int = 20,
        kind: str = "",
        damping: float = 0.85,
        iterations: int = 30,
    ) -> str:
        """PageRank — node importance, optionally personalised by query.

        Use for: knowledge condensation (top-N canonical concepts),
        query-personalised search ranking, documentation sourcing.

        Args:
            query: Optional personalisation query ("auth", "graph backend").
                   Empty = global PageRank.
            top: Max nodes returned (default 20).
            kind: Optional kind filter. Empty = all.
            damping: PageRank damping factor (default 0.85).
            iterations: Power-iteration count (default 30).

        Returns:
            JSON envelope with `nodes` ranked by PageRank score.
        """
        return _graph_tools.cos_graph_ranking(
            query=query or None,
            top=int(top),
            kind=kind or None,
            damping=float(damping),
            iterations=int(iterations),
        )

    @mcp.tool(
        name="cos_graph_cycles",
        annotations={
            "title": "Graph Circular Dependencies (SCC)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_cycles_tool(
        scope: str = "imports",
        top: int = 20,
        min_size: int = 2,
    ) -> str:
        """Detect circular dependencies as strongly-connected components.

        Args:
            scope: "imports" (module-level circular deps, the design smell) or
                "calls" (function cycles incl. legitimate mutual recursion).
            top: Max cycles returned (default 20).
            min_size: Minimum SCC size to report (default 2).

        Returns:
            JSON envelope with `cycles` (each {size, members}) + total_count.
        """
        return _graph_tools.cos_graph_cycles(
            scope=str(scope),
            top=int(top),
            min_size=int(min_size),
        )

    @mcp.tool(
        name="cos_graph_dead_code",
        annotations={
            "title": "Graph Dead-Code Candidates",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_dead_code_tool(
        kind: str = "",
        top: int = 50,
        include_tests: bool = False,
    ) -> str:
        """List in-repo symbols with zero non-test inbound references (dead-code candidates).

        Surfaces functions / methods / classes that nothing (outside tests)
        calls, constructs, subclasses, or type-references — the inverse of
        centrality. Candidates only: dynamic-dispatch / CLI-registered /
        externally-called symbols may appear; verify with cos_graph_references
        before deleting.

        Args:
            kind: Optional filter — function | method | class. Empty = all three.
            top: Max candidates returned (default 50, max 500).
            include_tests: Count test-sourced edges + include test files (default False).

        Returns:
            JSON envelope with `dead` (list) + `total_count`.
        """
        return _graph_tools.cos_graph_dead_code(
            kind=kind or "",
            top=int(top),
            include_tests=bool(include_tests),
        )

    @mcp.tool(
        name="cos_graph_test_gap",
        annotations={
            "title": "Graph Test-Gap (untested symbols)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_test_gap_tool(
        kind: str = "",
        top: int = 50,
    ) -> str:
        """List prod function/method/class with zero inbound edge from any test (untested symbols).

        Candidates only: indirect exercise (CLI / fixtures / dynamic dispatch)
        may not appear as a graph edge. Shell excluded (no call-graph).

        Args:
            kind: Optional filter — function | method | class. Empty = all three.
            top: Max returned (default 50, max 500).

        Returns:
            JSON envelope with `untested` (list) + total_count.
        """
        return _graph_tools.cos_graph_test_gap(kind=kind or "", top=int(top))

    @mcp.tool(
        name="cos_graph_diff",
        annotations={
            "title": "Graph Diff (git revision blast-radius)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_diff_tool(
        base: str = "HEAD~1",
        head: str = "HEAD",
        analyze_downstream: bool = True,
    ) -> str:
        """Graph blast-radius of a git revision range (base..head).

        Resolves changed files via `git diff --name-only base..head`, then maps
        them to affected symbols + downstream consumers + risk (PR/review view).

        Args:
            base: Base git revision (default HEAD~1).
            head: Head git revision (default HEAD).
            analyze_downstream: Walk transitive consumers (default True).

        Returns:
            JSON envelope with range, files, symbols, downstream_consumers, risk_level.
        """
        return _graph_tools.cos_graph_diff(
            base=str(base),
            head=str(head),
            analyze_downstream=bool(analyze_downstream),
        )

    @mcp.tool(
        name="cos_graph_doctor",
        annotations={
            "title": "Graph Health Doctor",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_doctor_tool(
        fix: bool = False,
    ) -> str:
        """Graph health snapshot — orphans, dangling edges, duplicates, backend status.

        Call when graph queries return nothing or `meta.backend_fallback=true`.

        Args:
            fix: If True, attempt safe repairs (delete dangling edges). Default False
                 — use the report-only mode to see what would change first.

        Returns:
            JSON envelope with `healthy` boolean, `issues` list, `stats` dict.
        """
        return _graph_tools.cos_graph_doctor(
            fix=bool(fix),
        )

else:
    register_unavailable_stubs(
        (
            "cos_graph_contracts",
            "cos_graph_entrypoints",
            "cos_graph_communities",
            "cos_graph_resolve",
            "cos_graph_centrality",
            "cos_graph_ranking",
            "cos_graph_cycles",
            "cos_graph_dead_code",
            "cos_graph_test_gap",
            "cos_graph_diff",
            "cos_graph_doctor",
        )
    )
