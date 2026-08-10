"""cos_graph_* lookup and traversal tools (query, context, impact, trace, export)."""

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
        name="cos_graph_query",
        annotations={
            "title": "Graph Symbol Lookup (known name/path/uid)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_query_tool(
        q: str,
        kinds: str = "",
        limit: int = 10,
        max_hops: int = 2,
        confidence_min: float = 0.3,
        include_spine: bool = False,
    ) -> str:
        """Look up a symbol by a KNOWN short term, path, or uid (lexical + graph expansion). For a natural-language DESCRIPTION of code whose name you don't know, use cos_graph_search instead.

        TIP: prefer SHORT terms ("sdk_dispatcher", "ClaudeSDKDispatcher.dispatch") or
        a literal path / uid. Long natural-language queries return weaker matches
        because the index is built from labels + docstrings, not free text.

        UID scheme (also accepted as `q`):
          code:file:<path> · code:function:<path>::<name> · code:class:<path>::<name>
          code:method:<path>::<class>.<name> · code:module:<dotted>
          doc:file:<path> · doc:heading:<path>#<slug>:<level> · folder:<path>

        When the query looks like a path or uid and the lexical pass
        returns nothing, the tool falls back to a direct uid lookup so
        the agent gets a single-item hit instead of empty results.

        Args:
            q: Short term, path, or uid (non-empty). NL queries work but degrade.
            kinds: Comma-separated filter of node kinds (e.g. "function,class,method"). Empty = all.
            limit: Max results (default 10).
            max_hops: Walk expansion depth (default 2).
            confidence_min: Edge confidence floor (default 0.3).
            include_spine: S3 — attach the CONTAINS-ancestor chain to each result for breadcrumbs.

        Returns:
            JSON envelope with `results` array. See docs/engineering/graph_os-queries.md.
        """
        return _graph_tools.cos_graph_query(
            q,
            kinds=_csv(kinds),
            limit=int(limit),
            max_hops=int(max_hops),
            confidence_min=float(confidence_min),
            include_spine=bool(include_spine),
        )

    @mcp.tool(
        name="cos_graph_context",
        annotations={
            "title": "Graph Neighbourhood",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_context_tool(
        uid_or_name: str,
        direction: str = "both",
        depth: int = 1,
        include_content: bool = False,
        include_evidence: bool = False,
        include_spine: bool = False,
    ) -> str:
        """Return callers + callees + siblings + referenced docs around a symbol.

        Args:
            uid_or_name: Node uid or fuzzy label. Uid scheme:
                ``code:file:<path>`` | ``code:function:<path>::<name>`` |
                ``code:class:<path>::<name>`` | ``code:module:<dotted>`` |
                ``doc:file:<path>`` | ``doc:heading:<path>#<slug>:<level>`` |
                ``folder:<path>``. Raw repo paths (``core/foo.py``) are
                auto-resolved to ``code:file:`` / ``doc:file:`` / ``folder:``;
                if all variants miss, a fuzzy label match is tried. Run
                ``cos_graph_query`` first to discover candidates.
            direction: "in" | "out" | "both".
            depth: BFS depth (default 1).
            include_content: When True, each returned node gains a ``content``
                field with source text read from ``file_path:start_line..end_line``
                (capped at 2000 chars, with ``truncated: bool``). Silently skipped
                when the file is missing or the node has no file_path. (B21)
            include_evidence: JOIN evidence rows (costs ~2× tokens).
            include_spine: S3 — pulls the CONTAINS-ancestor chain (file → folder → …)
                so the UI can render breadcrumbs.
        """
        return _graph_tools.cos_graph_context(
            uid_or_name,
            direction=str(direction),
            depth=int(depth),
            include_content=bool(include_content),
            include_evidence=bool(include_evidence),
            include_spine=bool(include_spine),
        )

    @mcp.tool(
        name="cos_graph_impact",
        annotations={
            "title": "Graph Blast-Radius",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_impact_tool(
        uid: str,
        direction: str = "downstream",
        depth: int = 3,
        confidence_min: float = 0.3,
        visit_limit: int = 500,
    ) -> str:
        """Group affected nodes by risk tier (will_break / should_review / context).

        Args:
            uid: Fully-qualified node uid. Scheme: ``code:file:<path>`` |
                ``code:function:<path>::<name>`` | ``code:class:<path>::<name>`` |
                ``code:module:<dotted>`` | ``doc:file:<path>`` | ``folder:<path>``.
                Raw repo paths (``core/foo.py``) are auto-resolved to
                ``code:file:`` / ``doc:file:`` / ``folder:``. If unsure, run
                ``cos_graph_query`` first to discover the right uid.
            direction: "downstream" (callers — break if `uid` changes) |
                "upstream" (deps `uid` calls/imports) | "both".
            depth: BFS hop limit (default 3).
            confidence_min: Drop edges below this score (default 0.3, matching the function + HTTP route).
            visit_limit: BFS node-visit cap (1..50000, default 500). Raise when meta.walk_truncated is true.
        """
        return _graph_tools.cos_graph_impact(
            uid,
            direction=str(direction),
            depth=int(depth),
            confidence_min=float(confidence_min),
            visit_limit=int(visit_limit),
        )

    @mcp.tool(
        name="cos_graph_detect_changes",
        annotations={
            "title": "Graph Pre-Commit Self-Review",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_detect_changes_tool(
        files: str = "",
        scope: str = "working",
        analyze_downstream: bool = True,
    ) -> str:
        """Map changed files to affected symbols + downstream tasks + risk level.

        Args:
            files: Comma-separated file paths (empty → echo empty envelope).
            scope: Label only; "working" | "staged" | "HEAD~1..HEAD".
            analyze_downstream: Walk transitive blast radius.
        """
        return _graph_tools.cos_graph_detect_changes(
            scope=str(scope),
            files=_csv(files),
            analyze_downstream=bool(analyze_downstream),
        )

    @mcp.tool(
        name="cos_graph_trace",
        annotations={
            "title": "Graph Execution Trace",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_trace_tool(
        entry_uid: str,
        terminals: str = "return,exception",
        max_steps: int = 50,
        include_external: bool = False,
    ) -> str:
        """Forward execution walk from `entry_uid` until terminals.

        Args:
            entry_uid: Function/method uid to start from, e.g.
                ``code:function:core/foo.py::bar``. Raw paths or names are
                auto-resolved (file → ``code:file:`` then entry-point heuristic).
                Run ``cos_graph_query`` first if unsure.
            terminals: Comma-separated edge labels that stop the walk.
            max_steps: Hard cap on emitted steps.
        """
        return _graph_tools.cos_graph_trace(
            entry_uid,
            terminals=tuple(_csv(terminals) or ("return", "exception")),
            max_steps=int(max_steps),
            include_external=bool(include_external),
        )

    @mcp.tool(
        name="cos_graph_similar",
        annotations={
            "title": "Graph Semantic Similarity",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_similar_tool(
        uid: str,
        top_k: int = 5,
        confidence_min: float = 0.5,
    ) -> str:
        """Return the top-K nodes most similar to `uid` (difflib baseline).

        Args:
            uid: Fully-qualified node uid (see ``cos_graph_impact`` for
                scheme). Raw repo paths are auto-resolved to
                ``code:file:`` / ``doc:file:`` / ``folder:``.
            top_k: Number of similar nodes to return.
            confidence_min: Minimum similarity score (0.0–1.0).
        """
        return _graph_tools.cos_graph_similar(
            uid,
            top_k=int(top_k),
            confidence_min=float(confidence_min),
        )

    @mcp.tool(
        name="cos_graph_search",
        annotations={
            "title": "Graph Semantic Search (by description)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_search_tool(
        query: str,
        top_k: int = 10,
    ) -> str:
        """Find code symbols from a NATURAL-LANGUAGE description (semantic + lexical + centrality). For a KNOWN name / path / uid, use cos_graph_query instead.

        Args:
            query: Natural-language or code-ish query (e.g. "validate jwt token").
            top_k: Number of results to return (1–50).
        """
        return _graph_tools.cos_graph_search(query, top_k=int(top_k))

    @mcp.tool(
        name="cos_graph_references",
        annotations={
            "title": "Graph Inbound References",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_references_tool(
        uid: str,
        kinds: str = "",
        limit: int = 100,
    ) -> str:
        """List inbound edges — "who references this?".

        Args:
            uid: Fully-qualified node uid. Scheme: ``code:file:<path>`` |
                ``code:function:<path>::<name>`` | ``code:class:<path>::<name>`` |
                ``code:module:<dotted>`` | ``doc:file:<path>`` | ``folder:<path>``.
                Raw repo paths are auto-resolved.
            kinds: Comma-separated edge types. Empty string (default)
                picks edge types automatically per node-kind — class
                nodes get ``constructs+has_param_type+is_decorated_by+inherits_from``,
                function/method get ``calls+accesses_field+imports``, files
                get ``imports+links_to+references_doc+contains``. R4-02.
            limit: Max edges returned (default 100).
        """
        parsed = tuple(_csv(kinds) or ())
        return _graph_tools.cos_graph_references(
            uid,
            kinds=parsed if parsed else None,
            limit=int(limit),
        )

    @mcp.tool(
        name="cos_graph_path",
        annotations={
            "title": "Graph Shortest Path",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_path_tool(
        source_uid: str,
        target_uid: str,
        max_hops: int = 5,
    ) -> str:
        """Shortest path between two nodes (either direction).

        Args:
            source_uid: Origin uid (auto-resolves raw paths; see
                ``cos_graph_impact`` for the scheme).
            target_uid: Destination uid (same rules as ``source_uid``).
            max_hops: BFS depth limit (default 5).
        """
        return _graph_tools.cos_graph_path(
            source_uid,
            target_uid,
            max_hops=int(max_hops),
        )

    @mcp.tool(
        name="cos_graph_export",
        annotations={
            "title": "Graph Subgraph Export",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_export_tool(
        format: str = "json",
        root_uid: str = "",
        edge_types: str = "",
        max_nodes: int = 500,
        include_spine: bool = False,
        mode: str = "auto",
        exclude_kinds: str = "__default__",
    ) -> str:
        """Export a subgraph as json | mermaid | dot.

        Args:
            format: Output format (``json`` / ``mermaid`` / ``dot``).
            root_uid: Optional seed; empty walks the edge table.
            edge_types: Comma-separated edge filter (empty = all).
            max_nodes: Hard cap on node count.
            include_spine: S3 — also include the CONTAINS ancestor chain.
            mode: TASK-141 view-mode blend when no root is pinned —
                ``auto`` (semantic + contains, default), ``containment``,
                ``dependencies``, or ``processes``.
            exclude_kinds: Comma-separated noise kinds to drop. Sentinel
                ``__default__`` (default) applies the built-in noise list;
                empty string disables filtering.
        """
        if exclude_kinds == "__default__":
            ek = None
        elif exclude_kinds == "":
            ek = []
        else:
            ek = list(_csv(exclude_kinds) or ())
        return _graph_tools.cos_graph_export(
            format=str(format),
            root_uid=root_uid or None,
            edge_types=_csv(edge_types),
            max_nodes=int(max_nodes),
            include_spine=bool(include_spine),
            mode=str(mode),
            exclude_kinds=ek,
        )

    @mcp.tool(
        name="cos_graph_rename_plan",
        annotations={
            "title": "Graph Rename Plan",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_rename_plan_tool(
        uid: str,
        new_name: str,
        check_strings: bool = True,
    ) -> str:
        """Plan a rename — call-sites, docs, tests, strings, risk.

        Args:
            uid: Symbol to rename. Scheme: ``code:function:<path>::<name>`` |
                ``code:class:<path>::<name>`` | ``code:module:<dotted>``.
                Raw paths are auto-resolved when applicable.
            new_name: Replacement symbol name.
            check_strings: Also scan string literals for the old name.
        """
        return _graph_tools.cos_graph_rename_plan(
            uid,
            new_name,
            check_strings=bool(check_strings),
        )

else:
    register_unavailable_stubs(
        (
            "cos_graph_query",
            "cos_graph_context",
            "cos_graph_impact",
            "cos_graph_detect_changes",
            "cos_graph_trace",
            "cos_graph_similar",
            "cos_graph_search",
            "cos_graph_references",
            "cos_graph_path",
            "cos_graph_export",
            "cos_graph_rename_plan",
        )
    )
