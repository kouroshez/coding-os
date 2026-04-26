"""graph-os CLI subcommands (Phase I.14).

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

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

import click


# ---------------------------------------------------------------------------
# Lazy bootstrap — push core/ + core/thinking_os onto sys.path.
# ---------------------------------------------------------------------------


def _bootstrap_paths() -> None:
    here = Path(__file__).resolve()
    core_dir = here.parent.parent / "core"
    tos_dir = core_dir / "thinking_os"
    for candidate in (core_dir, tos_dir):
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
    from db import init_db  # type: ignore
    from graph_os.backends.sqlite_backend import SqliteBackend  # type: ignore
    from graph_os.tools import graph as graph_tools  # type: ignore

    conn = init_db()
    backend = SqliteBackend(conn=conn)
    graph_tools._BACKEND_SINGLETON = backend
    return backend, graph_tools


# ---------------------------------------------------------------------------
# Query / context / impact / etc.
# ---------------------------------------------------------------------------


def register(cli: click.Group) -> None:
    """Attach every `cos graph-*` subcommand onto the parent `cli` group."""

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
    @click.option("--direction", default="downstream", type=click.Choice(["downstream", "upstream", "both"]))
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
    @click.option("--kinds", default="calls,accesses_field,imports,references_doc")
    @click.option("--limit", default=100, type=int)
    @click.option("--pretty", is_flag=True)
    def graph_references(uid, kinds, limit, pretty):
        """Inbound edges — who references this."""
        _, tools = _open_backend()
        _json_echo(
            tools.cos_graph_references(
                uid,
                kinds=tuple(k.strip() for k in kinds.split(",") if k.strip()),
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
        from db import get_db_stats  # type: ignore

        stats = get_db_stats(backend._conn)
        report = {
            "schema_version": stats["schema_version"],
            "node_count": backend.count_nodes(),
            "edge_count": backend.count_edges(),
            "backend": backend.backend_id,
            "db_size_bytes": stats.get("db_size_bytes"),
        }
        _json_echo(report, pretty=pretty)

    @cli.command(name="graph-reindex")
    @click.option("--path", default=None, help="Directory to reindex (default: repo root).")
    @click.option("--no-docs", is_flag=True, help="Skip the docs RAG layer.")
    @click.option("--max-files", default=5000, type=int)
    @click.option(
        "--force", "-f",
        is_flag=True,
        help="V1: bypass the file_index_state cache; reindex even "
        "files whose content_hash matches the last successful run.",
    )
    @click.option(
        "--status",
        is_flag=True,
        help="V1: print the top 50 most-recently-indexed files from "
        "file_index_state and exit (debugging aid).",
    )
    @click.option(
        "--rebuild-kinds",
        is_flag=True,
        help="S3: re-run the v16 kind-normalization data migration "
        "without a full reindex. Useful after the NodeKind enum "
        "ships to canonicalise legacy colon-prefixed kinds in place.",
    )
    @click.option(
        "--extractor",
        type=click.Choice(["auto", "legacy", "tree-sitter"], case_sensitive=False),
        default="auto",
        show_default=True,
        help=(
            "TASK-122 A/B flag: which parser ladder extractors should "
            "use. 'legacy' forces ast/regex baselines; 'tree-sitter' "
            "prefers tree-sitter when grammars are installed (lands "
            "in TASK-119/120/121); 'auto' picks the current default. "
            "Sets COS_EXTRACTOR_PREFERENCE for downstream extractors."
        ),
    )
    def graph_reindex(path, no_docs, max_files, force, status, rebuild_kinds, extractor):
        """Walk a directory and rebuild the graph via the dispatcher."""
        _bootstrap_paths()
        # TASK-122: publish the chosen ladder via env so every spawned
        # subprocess (incremental indexer, doc indexer, etc.) sees it.
        # Existing call sites that bypass the CLI (e.g. PostToolUse
        # auto-reindex) keep their default behaviour because the env
        # var is unset when the CLI flag isn't passed.
        os.environ["COS_EXTRACTOR_PREFERENCE"] = (extractor or "auto").lower()
        if status:
            _graph_reindex_print_status()
            return
        if rebuild_kinds:
            # S3 data migration — idempotent; can be invoked standalone.
            try:
                import db  # type: ignore
                from graph_os.types import normalize_kind  # type: ignore
            except ImportError as exc:
                click.echo(f"[graph-reindex] rebuild-kinds import failed: {exc}", err=True)
                return
            conn = db.get_connection()
            try:
                rows = conn.execute(
                    "SELECT DISTINCT kind FROM graph_nodes"
                ).fetchall()
                renames: dict[str, str] = {}
                for r in rows:
                    legacy = r[0]
                    if legacy is None:
                        continue
                    try:
                        canonical = normalize_kind(legacy).value
                    except ValueError:
                        continue
                    if canonical != legacy:
                        renames[legacy] = canonical
                total = 0
                for legacy, canonical in renames.items():
                    cur = conn.execute(
                        "UPDATE graph_nodes SET kind = ? WHERE kind = ?",
                        (canonical, legacy),
                    )
                    total += cur.rowcount or 0
                conn.commit()
                click.echo(
                    f"[graph-reindex] rebuild-kinds: "
                    f"{len(renames)} distinct kind(s) rewritten, "
                    f"{total} row(s) updated"
                )
                return
            finally:
                conn.close()

        import time as _time

        from graph_os.ingest import walk_local  # type: ignore
        from graph_os.tools.reindex_dispatch import dispatch  # type: ignore

        target = Path(path or Path.cwd()).resolve()
        plan = walk_local(target, max_files=max_files)
        click.echo(
            f"[graph-reindex] walking {target}; {len(plan.files)} files "
            f"(force={force})"
        )
        processed = skipped = errors = 0
        started = _time.monotonic()
        for file_path in plan.files:
            try:
                report = dispatch(
                    file_path,
                    project_root=target,
                    include_docs=not no_docs,
                    force=force,
                )
                cache = report.get("cache")
                if cache == "hit":
                    skipped += 1
                    click.echo(f"[graph-reindex]   · cache-hit {report['path']}")
                elif report.get("status") == "ok":
                    processed += 1
                else:
                    # skipped-no-layer etc. still counts as non-error
                    processed += 1
            except Exception as exc:  # noqa: BLE001
                errors += 1
                click.echo(f"[graph-reindex]   ! {file_path}: {exc}", err=True)
        duration = _time.monotonic() - started
        click.echo(
            f"[graph-reindex] processed={processed} skipped={skipped} "
            f"errors={errors} duration={duration:.2f}s"
        )

    @cli.command(name="graph-index-local")
    @click.argument("path")
    @click.option("--alias", default=None)
    @click.option("--max-files", default=50_000, type=int)
    @click.option("--max-size-mb", default=500, type=int)
    def graph_index_local(path, alias, max_files, max_size_mb):
        """Index a local folder (outside the current repo)."""
        _bootstrap_paths()
        from graph_os.ingest import walk_local  # type: ignore
        from graph_os.tools.reindex_dispatch import dispatch  # type: ignore

        target = Path(path).expanduser().resolve()
        plan = walk_local(
            target,
            alias=alias,
            max_files=max_files,
            max_size_bytes=max_size_mb * 1024 * 1024,
        )
        click.echo(f"[local] alias={plan.alias} files={len(plan.files)}")
        indexed = 0
        for file_path in plan.files:
            report = dispatch(file_path, project_root=target, include_docs=True)
            if report.get("status") == "ok":
                indexed += 1
        click.echo(f"[local] indexed {indexed}/{len(plan.files)}")

    @cli.command(name="graph-index-github")
    @click.argument("url")
    @click.option("--branch", default=None)
    @click.option("--alias", default=None)
    @click.option("--auth", default=None, help="Token for private repos (never logged).")
    @click.option("--max-size-mb", default=500, type=int)
    @click.option("--timeout", default=300, type=int)
    def graph_index_github(url, branch, alias, auth, max_size_mb, timeout):
        """Clone a public GitHub repo + index (shallow by default)."""
        _bootstrap_paths()
        from graph_os.ingest import GithubSize, clone_github  # type: ignore
        from graph_os.tools.reindex_dispatch import dispatch  # type: ignore

        plan = clone_github(
            url,
            branch=branch,
            alias=alias,
            auth=auth,
            size=GithubSize(
                max_size_bytes=max_size_mb * 1024 * 1024,
                timeout_seconds=timeout,
            ),
        )
        click.echo(f"[github] alias={plan.alias} files={len(plan.files)}")
        indexed = 0
        for file_path in plan.files:
            report = dispatch(file_path, project_root=plan.root, include_docs=True)
            if report.get("status") == "ok":
                indexed += 1
        click.echo(f"[github] indexed {indexed}/{len(plan.files)}")

    @cli.command(name="graph-index-zip")
    @click.argument("archive")
    @click.option("--alias", default=None)
    @click.option("--out-dir", default=None, help="Extraction root (default tmp).")
    @click.option("--max-size-mb", default=500, type=int)
    def graph_index_zip(archive, alias, out_dir, max_size_mb):
        """Extract a ZIP archive with bomb protection + index."""
        _bootstrap_paths()
        from graph_os.ingest import ZipSize, extract_zip  # type: ignore
        from graph_os.tools.reindex_dispatch import dispatch  # type: ignore

        out = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="cos-zip-"))
        plan = extract_zip(
            archive,
            alias=alias,
            out_dir=out,
            size=ZipSize(max_size_bytes=max_size_mb * 1024 * 1024),
        )
        click.echo(f"[zip] alias={plan.alias} files={len(plan.files)}")
        indexed = 0
        for file_path in plan.files:
            report = dispatch(file_path, project_root=plan.root, include_docs=True)
            if report.get("status") == "ok":
                indexed += 1
        click.echo(f"[zip] indexed {indexed}/{len(plan.files)}")

    @cli.command(name="graph-detect-changes")
    @click.option(
        "--staged",
        "mode",
        flag_value="staged",
        help="Diff staged changes (git diff --cached --name-only).",
    )
    @click.option(
        "--working",
        "mode",
        flag_value="working",
        default=True,
        help="Diff working-tree changes (git diff --name-only). [default]",
    )
    @click.option(
        "--range",
        "git_range",
        default=None,
        metavar="RANGE",
        help="Diff a commit range, e.g. HEAD~1..HEAD (git diff --name-only RANGE).",
    )
    @click.option("--pretty", is_flag=True)
    def graph_detect_changes(mode, git_range, pretty):
        """Map changed files to affected graph symbols + downstream tasks.

        PURPOSE:  B24 CLI wrapper for cos_graph_detect_changes. Runs the
                  appropriate git diff --name-only command and forwards the
                  resulting file list to the MCP tool, which walks the graph
                  to surface affected symbols, downstream tasks, and risk level.
        INPUT:    --staged | --working (default) | --range RANGE
        OUTPUT:   JSON envelope matching cos_graph_detect_changes.
        DEPENDENCIES:  git on PATH; graph-os SQLite backend.
        NOTES:    When no changed files are found the tool returns an empty
                  envelope (risk_level=none) rather than an error.
        """
        import subprocess  # noqa: PLC0415

        # Build the git command based on selected mode.
        if git_range:
            scope = git_range
            git_cmd = ["git", "diff", "--name-only", git_range]
        elif mode == "staged":
            scope = "staged"
            git_cmd = ["git", "diff", "--cached", "--name-only"]
        else:
            scope = "working"
            git_cmd = ["git", "diff", "--name-only"]

        try:
            result = subprocess.run(
                git_cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise click.ClickException(
                    f"git exited {result.returncode}: {result.stderr.strip()}"
                )
            files = [
                line.strip()
                for line in result.stdout.splitlines()
                if line.strip()
            ]
        except FileNotFoundError:
            raise click.ClickException("git not found on PATH")
        except subprocess.TimeoutExpired:
            raise click.ClickException("git diff timed out after 30 s")

        _, tools = _open_backend()
        _json_echo(
            tools.cos_graph_detect_changes(
                scope=scope,
                files=files or None,
                analyze_downstream=True,
            ),
            pretty=pretty,
        )

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

    @cli.command(name="graph-viz")
    @click.option("--path", default=None)
    @click.option("--out", default=None, help="Output HTML path.")
    @click.option("--root-uid", default=None)
    @click.option("--title", default="graph-os")
    @click.option("--bundled", is_flag=True)
    @click.option("--serve", is_flag=True)
    @click.option("--port", default=0, type=int)
    @click.option("--open/--no-open", "open_browser", default=True)
    def graph_viz(path, out, root_uid, title, bundled, serve, port, open_browser):
        """Generate the HTML graph viewer and optionally open / serve it."""
        _bootstrap_paths()
        from graph_os.ingest import walk_local  # type: ignore
        from graph_os.tools.reindex_dispatch import dispatch  # type: ignore
        from graph_os.viewer import build_view  # type: ignore

        backend, _ = _open_backend()
        if path:
            target = Path(path).expanduser().resolve()
            plan = walk_local(target, max_files=5000)
            for file_path in plan.files:
                dispatch(file_path, project_root=target, include_docs=True)

        out_path = Path(out or Path(".coding-os") / "graph-viz.html").resolve()
        build_view(backend, out_path, title=title, root_uid=root_uid, bundled=bundled)
        click.echo(f"[graph-viz] wrote {out_path}")
        if serve:
            _serve_static(out_path, port=port, open_browser=open_browser)
        elif open_browser:
            import webbrowser

            webbrowser.open(out_path.as_uri())

    # ── group family --------------------------------------------------
    @cli.group(name="graph-group")
    def graph_group():
        """Cross-repo group operations."""

    @graph_group.command("create")
    @click.argument("name")
    @click.option("--manifest-dir", default=None, help="Root for ~/.coding-os/groups/<name>/ overrides.")
    def group_create(name, manifest_dir):
        _bootstrap_paths()
        from graph_os.groups import GroupManifest, save_manifest  # type: ignore

        target = _group_manifest_path(name, manifest_dir)
        if target.exists():
            raise click.ClickException(f"group already exists at {target}")
        save_manifest(GroupManifest(name=name, members=[]), target)
        click.echo(f"[group] created {target}")

    @graph_group.command("add")
    @click.argument("name")
    @click.argument("path")
    @click.option("--alias", default=None)
    @click.option("--owns-route", multiple=True)
    @click.option("--manifest-dir", default=None)
    def group_add(name, path, alias, owns_route, manifest_dir):
        _bootstrap_paths()
        from graph_os.groups import load_manifest, register_member, save_manifest  # type: ignore

        target = _group_manifest_path(name, manifest_dir)
        if not target.exists():
            raise click.ClickException("group missing; run `cos graph-group create` first")
        manifest = load_manifest(target)
        alias = alias or Path(path).expanduser().resolve().name
        manifest = register_member(
            manifest,
            alias=alias,
            path=str(Path(path).expanduser().resolve()),
            owned_routes=list(owns_route),
        )
        save_manifest(manifest, target)
        click.echo(f"[group] added {alias} to {name}")

    @graph_group.command("list")
    @click.option("--manifest-dir", default=None)
    def group_list(manifest_dir):
        base = _group_root(manifest_dir)
        if not base.exists():
            click.echo("(no groups)")
            return
        for entry in sorted(base.iterdir()):
            if entry.is_dir() and (entry / "group.json").exists():
                click.echo(entry.name)

    @graph_group.command("status")
    @click.argument("name")
    @click.option("--manifest-dir", default=None)
    def group_status(name, manifest_dir):
        _bootstrap_paths()
        from graph_os.groups import load_manifest  # type: ignore

        target = _group_manifest_path(name, manifest_dir)
        if not target.exists():
            raise click.ClickException("group missing")
        manifest = load_manifest(target)
        payload = {
            "name": manifest.name,
            "members": [
                {
                    "alias": m.alias,
                    "path": m.path,
                    "exists": Path(m.path).exists(),
                    "owned_routes": m.owned_routes,
                }
                for m in manifest.members
            ],
        }
        click.echo(json.dumps(payload, indent=2))

    @graph_group.command("sync")
    @click.argument("name")
    @click.option("--manifest-dir", default=None)
    def group_sync(name, manifest_dir):
        _bootstrap_paths()
        from graph_os.groups import load_manifest  # type: ignore
        from graph_os.ingest import walk_local  # type: ignore
        from graph_os.tools.reindex_dispatch import dispatch  # type: ignore

        target = _group_manifest_path(name, manifest_dir)
        manifest = load_manifest(target)
        indexed = 0
        for member in manifest.members:
            root = Path(member.path)
            if not root.exists():
                click.echo(f"[sync] skip {member.alias} (missing: {root})", err=True)
                continue
            plan = walk_local(root)
            for file_path in plan.files:
                report = dispatch(file_path, project_root=root, include_docs=True)
                if report.get("status") == "ok":
                    indexed += 1
            click.echo(f"[sync] {member.alias}: {len(plan.files)} files")
        click.echo(f"[sync] indexed {indexed} entries total")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _group_root(manifest_dir: str | None) -> Path:
    return Path(manifest_dir).expanduser() if manifest_dir else (
        Path.home() / ".coding-os" / "groups"
    )


def _group_manifest_path(name: str, manifest_dir: str | None) -> Path:
    root = _group_root(manifest_dir)
    root.mkdir(parents=True, exist_ok=True)
    folder = root / name
    folder.mkdir(exist_ok=True)
    return folder / "group.json"


def _graph_reindex_print_status() -> None:
    """V1 ``--status``: print top 50 most-recently-indexed file_index_state rows.

    PURPOSE:      Debugging aid — surface the per-file cache state so a
                  human can spot stale hashes, stuck errors, or files
                  that never re-indexed after a change.
    INPUT:        none (uses the default thinking-os.db lookup path).
    OUTPUT:       stdout table (file, hash[:12], indexed_at, status).
    DEPENDENCIES: core/thinking_os/db.py (init_db),
                  file_index_state table (migration v17).
    NOTES:        Degrades gracefully when the table or DB is missing.
    """
    from datetime import datetime

    _bootstrap_paths()
    try:
        import db  # type: ignore
    except ImportError as exc:
        raise click.ClickException(f"thinking-os db import failed: {exc}") from exc
    conn = db.init_db()
    try:
        if not db.has_file_index_state_table(conn):
            click.echo(
                "[graph-reindex] file_index_state table missing "
                "(migration v17 not applied)."
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

    click.echo(
        f"{'file_path':<60}  {'hash':<12}  {'indexed_at':<20}  status"
    )
    click.echo("-" * 110)
    for file_path, chash, chain, ts, err in rows:
        when = datetime.fromtimestamp(int(ts)).isoformat(timespec="seconds")
        status = "error" if err else "ok"
        chain_hint = chain[:20] + ("…" if len(chain) > 20 else "")
        display = f"{file_path} [{chain_hint}]"
        if len(display) > 60:
            display = display[:57] + "..."
        click.echo(f"{display:<60}  {chash[:12]:<12}  {when:<20}  {status}")


def _serve_static(path: Path, *, port: int, open_browser: bool) -> None:
    import socket
    import webbrowser
    from http.server import HTTPServer, SimpleHTTPRequestHandler

    os.chdir(path.parent)

    class _Handler(SimpleHTTPRequestHandler):
        def log_message(self, *_args, **_kwargs):
            pass

    if port == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
    httpd = HTTPServer(("127.0.0.1", port), _Handler)
    url = f"http://127.0.0.1:{port}/{path.name}"
    click.echo(f"[serve] {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
        click.echo("\n[serve] bye")


__all__ = ["register"]
