"""First doc + graph index runs for a freshly-scaffolded project.

Both seed a retrieval store so `cos_doc_search` and `cos_graph_*` answer from
the very first session, and both are non-fatal: a missing extra or a slow repo
degrades to an empty index plus a repair HINT, never a half-created project.
Sequencing the scaffold steps that precede them is `_init_phase`'s job.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import click

from cli._init_registries import CORE_DIR


def _initial_doc_index(project: Path, state: Path) -> None:
    """Seed document_chunks + FTS for a freshly-scaffolded project."""
    rag_config = state / "rag-config.yaml"
    if not rag_config.exists():
        return
    db_path = state / "coding-os.db"
    brain_dir = str(CORE_DIR / "thinking_os")
    code = (
        "import sys; "
        f"sys.path.insert(0, {brain_dir!r}); "
        "from database import init_db; "
        "from doc_indexer import index_docs; "
        "from pathlib import Path; "
        f"conn = init_db({str(db_path)!r}); "
        f"stats = index_docs(conn, Path({str(rag_config)!r}), Path({str(project)!r})); "
        "conn.close(); "
        "print(f\"  Indexed {stats['updated_files']} doc(s), {stats['new_chunks']} chunk(s)\")"
    )
    env = os.environ.copy()
    env["COS_DB_PATH"] = str(db_path)
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        click.echo(result.stdout.rstrip())
    elif result.returncode != 0:
        # Non-fatal: missing yaml / embeddings extras shouldn't break init.
        click.echo(
            f"  WARN: initial doc index skipped: {result.stderr.strip().splitlines()[-1] if result.stderr else 'unknown'}",
            err=True,
        )
        click.echo(
            "  HINT: doc search stays empty until indexed — install extras with "
            "`uv sync --extra rag` in the coding-os checkout, then run `make docs-index` here",
            err=True,
        )


def _initial_graph_index(project: Path, state: Path) -> None:
    """Build the knowledge graph for a fresh project when the graph module is on (TASK-423)."""
    try:
        from cli.subsystems import module_state

        if not module_state(project).get("graph", True):
            click.echo("  Skipped graph index (graph module disabled)")
            return
    except Exception:
        # State unreadable → graph is on by default; fall through and build.
        pass
    db_path = state / "coding-os.db"
    core_path = str(CORE_DIR)
    brain_dir = str(CORE_DIR / "thinking_os")
    # include_docs=False: the docs RAG layer was just seeded by
    # _initial_doc_index; here we want only the graph (AST + doc structure),
    # which needs no embedding model. Runs in-process python (sys.executable),
    # NOT the global `cos`, so an env without the graph deps fails fast instead
    # of doing heavy work (mirrors _initial_doc_index).
    code = (
        "import sys; "
        f"sys.path.insert(0, {core_path!r}); "
        f"sys.path.insert(0, {brain_dir!r}); "
        "from graph_os.ingest.base import walk_local; "
        "from graph_os.tools.reindex_dispatch import dispatch; "
        f"plan = walk_local({str(project)!r}); "
        "reports = [dispatch(str(f), project_root="
        f"{str(project)!r}, db_path={str(db_path)!r}, "
        "include_docs=False, link_stubs=True) for f in plan.files]; "
        "ok = sum(1 for r in reports if r.get('status') == 'ok'); "
        "print(f'  Built knowledge graph: {ok}/{len(reports)} file(s) indexed')"
    )
    env = os.environ.copy()
    env["COS_DB_PATH"] = str(db_path)
    # Bounded so a very large repo never blows the init budget (the Hub Composer
    # wraps `cos init` in its own timeout). On timeout the graph is left empty —
    # valid, since cos_graph_export returns ok([]) for an empty graph — with a
    # clear repair HINT, far better than hard-failing a half-created project.
    timeout_s = int(os.environ.get("COS_INIT_GRAPH_TIMEOUT", "180"))
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        click.echo(
            f"  WARN: initial graph index exceeded {timeout_s}s — graph left empty", err=True
        )
        click.echo("  HINT: graph stays empty until built — run `cos graph-reindex` here", err=True)
        return
    if result.returncode == 0 and result.stdout.strip():
        click.echo(result.stdout.rstrip())
    elif result.returncode != 0:
        # Non-fatal: missing graph deps shouldn't break init.
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown"
        click.echo(f"  WARN: initial graph index skipped: {detail}", err=True)
        click.echo(
            "  HINT: graph stays empty until built — run `cos graph-reindex` here",
            err=True,
        )
