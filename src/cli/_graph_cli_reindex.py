"""`cos graph-reindex` and its parallel dispatch worker."""

from __future__ import annotations

import json
import os
from pathlib import Path

import click

from cli._graph_cli_shared import (
    _bootstrap_paths,
    _graph_reindex_print_status,
)

# ---------------------------------------------------------------------------
# Parallel reindex worker — must be module-level so ProcessPoolExecutor
# can pickle it. Each worker re-imports graph_os.tools.reindex_dispatch
# inside its own process; init_db() inside dispatch() opens a fresh
# SQLite WAL connection. The dispatcher's busy-retry loop handles
# concurrent writers without the CLI having to coordinate.
# ---------------------------------------------------------------------------


def _report_failure_reason(report: dict) -> str | None:
    graph_layer = (report.get("layers") or {}).get("graph") or {}
    if report.get("status") == "error" or graph_layer.get("status") == "error":
        return str(graph_layer.get("reason") or report.get("reason") or "unknown")
    return None


def _is_lock_shaped(reason: str) -> bool:
    lowered = reason.lower()
    return "locked" in lowered or "busy" in lowered


def _parallel_dispatch(
    file_path: str,
    project_root: str,
    include_docs: bool,
    force: bool,
) -> dict:
    _bootstrap_paths()
    from graph_os.tools.reindex_dispatch import dispatch  # type: ignore

    # defer per-file stub linking — graph_reindex runs ONE global
    # link after the whole walk, so mid-walk resolutions aren't orphaned by a
    # later file's prune-before-reindex.
    return dispatch(
        file_path,
        project_root=project_root,
        include_docs=include_docs,
        force=force,
        link_stubs=False,
    )


def register_reindex(cli: click.Group) -> None:
    """Attach this slice of the `cos graph-*` family onto `cli`."""

    @cli.command(name="graph-reindex")
    @click.option("--path", default=None, help="Directory to reindex (default: repo root).")
    @click.option("--no-docs", is_flag=True, help="Skip the docs RAG layer.")
    @click.option(
        "--max-files",
        default=1_000_000,
        type=int,
        help="Cap on files walked (default 1M for monorepo-scale).",
    )
    @click.option(
        "--workers",
        "-j",
        default=1,
        type=int,
        help="Parallel worker processes (default 1 = sequential). For "
        "large monorepos, set to CPU count (e.g. -j 8). SQLite WAL + "
        "the dispatcher's lock-retry loop handle concurrent writes.",
    )
    @click.option(
        "--force",
        "-f",
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
    @click.option(
        "--prune-stale",
        is_flag=True,
        help=(
            "W7.5 / R4-N7: delete nodes whose file_path no longer exists "
            "on disk BEFORE reindexing. Reindex is idempotent-upsert so "
            "moved/renamed/deleted files leave ghost nodes that bloat "
            "the graph; this flag invokes cos_graph_doctor(fix=True) "
            "to prune them first."
        ),
    )
    def graph_reindex(
        path,
        no_docs,
        max_files,
        workers,
        force,
        status,
        rebuild_kinds,
        extractor,
        prune_stale,
    ):
        """Walk a directory and rebuild the graph via the dispatcher."""
        _bootstrap_paths()
        # publish the chosen ladder via env so every spawned
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
                import database  # type: ignore

                from graph_os.types import normalize_kind  # type: ignore
            except ImportError as exc:
                click.echo(f"[graph-reindex] rebuild-kinds import failed: {exc}", err=True)
                return
            conn = database.get_connection()
            try:
                rows = conn.execute("SELECT DISTINCT kind FROM graph_nodes").fetchall()
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

        # W7.5 / R4-N7: prune stale-path nodes before reindex when asked.
        if prune_stale:
            from graph_os.tools.graph import cos_graph_doctor  # type: ignore

            doc = cos_graph_doctor(fix=True)
            # cos_graph_doctor returns a JSON string (FastMCP wire); parse
            # it before reading nested fields.
            if isinstance(doc, str):
                doc = json.loads(doc)
            fixed = doc.get("data", {}).get("meta", {}).get("fixed_count", 0)
            click.echo(f"[graph-reindex] prune-stale: removed {fixed} stale node(s)")

        target = Path(path or Path.cwd()).resolve()
        # --path is the WALK directory, not the project root. Resolve the
        # enclosing repo root (nearest ancestor with .coding-os/) so a
        # sub-dir --path can't spawn a stray <subdir>/.coding-os/ DB or
        # emit subdir-relative file_paths.
        project_root = next(
            (p for p in (target, *target.parents) if (p / ".coding-os").is_dir()),
            target,
        )
        plan = walk_local(target, max_files=max_files)
        click.echo(f"[graph-reindex] walking {target}; {len(plan.files)} files (force={force})")
        # Surface oversized files dropped by the per-file byte cap — a skipped
        # large source file is a coverage gap, not a no-op.
        _oversize = plan.metadata.get("skipped_oversize") or []
        if _oversize:
            click.echo(
                f"[graph-reindex] skipped {len(_oversize)} oversized file(s) "
                f"(> COS_GRAPH_MAX_FILE_BYTES): {', '.join(_oversize[:5])}"
                + (" …" if len(_oversize) > 5 else ""),
                err=True,
            )
        # Symlink / unreadable skips — counts only, surfaced so they aren't
        # silent. A symlink target is indexed on its own pass, so
        # a non-zero symlink count is informational, not an error.
        _sym = int(plan.metadata.get("skipped_symlink") or 0)
        _rerr = int(plan.metadata.get("skipped_read_error") or 0)
        if _sym or _rerr:
            click.echo(
                f"[graph-reindex] skipped {_sym} symlink(s), {_rerr} unreadable file(s)",
                err=True,
            )
        processed = skipped = errors = lock_streak = 0
        failed_paths: list[str] = []
        started = _time.monotonic()
        # Circuit breaker: a write lock held by another process makes EVERY
        # file fail after its bounded busy-wait (~5s × 3 retries). Without
        # this, an 800-file walk grinds silently for an hour — the per-file
        # failure used to land only in layers.graph.status, which this loop
        # counted as PROCESSED (the 2026-06-11 stall). The streak
        # resets on any success so a transient start-of-walk lock storm
        # (workers warming up alongside hub/MCP writers) doesn't abort a
        # run that is actually progressing.
        _LOCK_STREAK_ABORT = 10

        def _record(report: dict) -> None:
            nonlocal processed, skipped, errors, lock_streak
            cache = report.get("cache")
            if cache == "hit":
                skipped += 1
                return
            processed += 1
            reason = _report_failure_reason(report)
            if reason is None:
                lock_streak = 0
                return
            errors += 1
            failed_paths.append(str(report.get("path") or ""))
            if errors <= 5:
                click.echo(f"[graph-reindex]   ! {report.get('path')}: {reason}", err=True)
            if _is_lock_shaped(reason):
                lock_streak += 1
            if lock_streak >= _LOCK_STREAK_ABORT:
                raise click.ClickException(
                    f"aborting: {lock_streak} consecutive lock-shaped graph write "
                    "failures — another process is holding the DB write lock; "
                    "close it and re-run"
                )

        # Live per-file progress bar — click.progressbar auto-hides when
        # stdout is not a TTY (pipes / CI), so non-interactive runs keep
        # the summary-only output. Replaces the per-file cache-hit echo.
        bar = click.progressbar(length=len(plan.files), label="[graph-reindex] indexing")
        if workers and workers > 1:
            # ProcessPoolExecutor parallelism for monorepo-scale walks. Each
            # worker opens its own SQLite connection via init_db() inside
            # dispatch(); WAL mode + the dispatcher's busy-retry loop handle
            # concurrent writers.
            from concurrent.futures import ProcessPoolExecutor, as_completed

            click.echo(f"[graph-reindex] parallel workers={workers}")
            futures = {}
            with ProcessPoolExecutor(max_workers=workers) as pool, bar:
                for file_path in plan.files:
                    fut = pool.submit(
                        _parallel_dispatch,
                        str(file_path),
                        str(project_root),
                        not no_docs,
                        force,
                    )
                    futures[fut] = file_path
                for fut in as_completed(futures):
                    file_path = futures[fut]
                    try:
                        report = fut.result()
                        _record(report)
                    except click.ClickException:
                        # Circuit breaker tripped — drop queued work NOW;
                        # the context manager's shutdown(wait=True) would
                        # otherwise grind through every pending future.
                        pool.shutdown(wait=False, cancel_futures=True)
                        raise
                    except Exception as exc:
                        errors += 1
                        failed_paths.append(str(file_path))
                        click.echo(f"[graph-reindex]   ! {file_path}: {exc}", err=True)
                    bar.update(1)
        else:
            with bar:
                for file_path in plan.files:
                    try:
                        report = dispatch(
                            file_path,
                            project_root=project_root,
                            include_docs=not no_docs,
                            force=force,
                            link_stubs=False,  # global link after the walk
                        )
                        _record(report)
                    except click.ClickException:
                        raise
                    except Exception as exc:
                        errors += 1
                        failed_paths.append(str(file_path))
                        click.echo(f"[graph-reindex]   ! {file_path}: {exc}", err=True)
                    bar.update(1)

        # Writers serialize in SQLite, so parallel workers can drop a few
        # files to lock contention (their hash is NOT advanced). Retry the
        # casualties sequentially — no sibling contention — so a parallel
        # walk converges to the same zero-error result as a sequential one.
        if failed_paths:
            recovered = 0
            for rel in [p for p in failed_paths if p]:
                try:
                    report = dispatch(
                        project_root / rel,
                        project_root=project_root,
                        include_docs=not no_docs,
                        force=force,
                        link_stubs=False,
                    )
                    if _report_failure_reason(report) is None:
                        recovered += 1
                except Exception as exc:
                    click.echo(f"[graph-reindex]   ! retry {rel}: {exc}", err=True)
            errors -= recovered
            click.echo(f"[graph-reindex] retry pass: {recovered}/{len(failed_paths)} recovered")
        duration = _time.monotonic() - started

        # Reconcile the graph to the current walk BEFORE reporting: file_index_state
        # rows (and their nodes/edges) for files no longer indexed — deleted from
        # disk OR now excluded by .gitignore — are stale and make cos_graph_doctor
        # over-count. GC them first so the parse-error summary below reads the
        # reconciled (exact) state. ONLY on a full, uncapped repo walk
        # (target == project_root); a --path sub-walk or a max_files-capped walk
        # would wrongly flag every other file as stale.
        if target == project_root and len(plan.files) < max_files:
            try:
                from database import init_db, resolve_db_path  # type: ignore

                gc_conn = init_db(str(resolve_db_path(project_root)))
                walked = {p.relative_to(project_root).as_posix() for p in plan.files}
                stale = [
                    r[0]
                    for r in gc_conn.execute(
                        "SELECT DISTINCT file_path FROM file_index_state"
                    ).fetchall()
                    if r[0] and r[0] not in walked
                ]
                gc_nodes = 0
                for sp in stale:
                    gc_conn.execute(
                        "DELETE FROM graph_edges_v12 WHERE source_id IN "
                        "(SELECT id FROM graph_nodes WHERE file_path=?) "
                        "OR target_id IN (SELECT id FROM graph_nodes WHERE file_path=?)",
                        (sp, sp),
                    )
                    cur = gc_conn.execute("DELETE FROM graph_nodes WHERE file_path=?", (sp,))
                    gc_nodes += cur.rowcount or 0
                    gc_conn.execute("DELETE FROM file_index_state WHERE file_path=?", (sp,))
                if stale:
                    gc_conn.commit()
                    click.echo(
                        f"[graph-reindex] reconcile: pruned {len(stale)} no-longer-indexed "
                        f"file(s), {gc_nodes} node(s)"
                    )
            except Exception as exc:
                click.echo(f"[graph-reindex] reconcile skipped: {exc}", err=True)

        # Surface partial-extraction coverage gaps (some symbols dropped on a
        # parse error) — "errors" only counts hard exceptions, so this was
        # silent. Read the cumulative truth from file_index_state,
        # the same source cos_graph_doctor reports, so the two always agree.
        parse_err_total = parse_err_files = 0
        try:
            from database import init_db, resolve_db_path  # type: ignore

            _pe_conn = init_db(str(resolve_db_path(project_root)))
            _pe_row = _pe_conn.execute(
                "SELECT COALESCE(SUM(parse_errors_count), 0), COUNT(DISTINCT file_path) "
                "FROM file_index_state WHERE parse_errors_count > 0"
            ).fetchone()
            parse_err_total = int(_pe_row[0] or 0)
            parse_err_files = int(_pe_row[1] or 0)
        except Exception as exc:  # fail-open — never block the summary
            import logging

            logging.getLogger("graph_os.cli").debug("parse-error summary probe skipped: %s", exc)
        click.echo(
            f"[graph-reindex] processed={processed} skipped={skipped} "
            f"errors={errors} parse_errors={parse_err_total} in {parse_err_files} files "
            f"duration={duration:.2f}s"
        )

        # per-file linking during the walk cannot resolve a stub
        # whose real target is indexed LATER (file-order dependency), so
        # cross-module bare-name calls (ok()/fail()/...) leak to external
        # stubs and references/impact under-report callers. Run the GLOBAL
        # linker once now that every node exists — same precise module→file
        # matching as the per-file pass, just applied across the whole graph.
        try:
            _bootstrap_paths()
            from database import init_db, resolve_db_path  # type: ignore

            from graph_os.backends.sqlite_backend import SqliteBackend  # type: ignore

            # Link the same DB the walk indexed — the repo-root DB, NOT a
            # <target>/.coding-os/ stray when --path points at a sub-dir.
            conn = init_db(str(resolve_db_path(project_root)))
            backend = SqliteBackend(conn=conn)
            relinked = backend.link_external_stubs()
            imports_linked = backend.link_import_bindings()
            php_linked = backend.link_php_handlers()
            click.echo(
                f"[graph-reindex] cross-file link: {relinked} stub(s) resolved, "
                f"{imports_linked} import binding(s)"
                + (f" (+{php_linked} php handler(s))" if php_linked else "")
            )
        except Exception as exc:
            click.echo(f"[graph-reindex] cross-file link skipped: {exc}", err=True)

        # Residue sweep — the file reconcile above reads file_index_state,
        # which holds file rows only, so folder-spine nodes and zero-edge
        # phantoms (a folder is not a file row; a phantom carries a NULL /
        # off-tree file_path) survive it. A bulk `git mv` / `rm -rf` of a
        # directory fires no per-file deletion-prune, so only this
        # authoritative full-walk pass clears the old-path folder/phantom
        # residue. Runs AFTER the global link so a live external stub already
        # holds its edges and is never swept; the doctor safe-repair deletes
        # only absent-on-disk paths and zero-edge orphans, so an on-disk
        # `src/`-prefixed node with `contains` edges survives. Same full-walk
        # guard as the file reconcile — a sub-walk / capped walk is not
        # authoritative.
        if target == project_root and len(plan.files) < max_files:
            try:
                from graph_os.tools.graph import cos_graph_doctor  # type: ignore

                swept = cos_graph_doctor(fix=True)
                if isinstance(swept, str):
                    swept = json.loads(swept)
                swept_n = swept.get("data", {}).get("meta", {}).get("fixed_count", 0)
                if swept_n:
                    click.echo(
                        f"[graph-reindex] reconcile-sweep: pruned {swept_n} "
                        "residual folder/phantom node(s)"
                    )
            except Exception as exc:
                click.echo(f"[graph-reindex] reconcile-sweep skipped: {exc}", err=True)
