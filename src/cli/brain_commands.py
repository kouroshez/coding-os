"""CLI subcommands that invoke thinking_os brain modules.

These exist so project Makefiles can call `cos docs-index` / `cos task-sync`
/ `cos reindex` without hardcoding the coding-os install path. The `cos`
binary itself knows where its own source lives
(`Path(__file__).resolve().parent.parent.parent`), so no burn-in is required.

Each subcommand is a thin wrapper over a `_main()` function in a brain
module. We call it via subprocess so the brain's sys.path manipulation
and optional `rag` extras load correctly.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import click

CODING_OS_ROOT = Path(__file__).resolve().parent.parent.parent
BRAIN_DIR = CODING_OS_ROOT / "src" / "core" / "thinking_os"

DOC_INDEXER = BRAIN_DIR / "doc_indexer.py"
TASK_SYNC = BRAIN_DIR / "task_sync.py"
EMBEDDINGS = BRAIN_DIR / "embeddings.py"
GRAPH_INDEXER = BRAIN_DIR / "graph_indexer.py"
DECAY_SCRIPT = BRAIN_DIR / "decay.py"
GC_SCRIPT = BRAIN_DIR / "memory_gc.py"


def _resolve_project_dir(raw: str) -> Path:
    """Resolve a project directory path, honouring --directory / $PWD."""
    if raw != ".":
        return Path(raw).resolve()
    shell_pwd = os.environ.get("PWD")
    if shell_pwd and Path(shell_pwd).is_dir():
        return Path(shell_pwd).resolve()
    return Path.cwd().resolve()


def _run_brain_module(
    script: Path,
    args: list[str],
    *,
    project: Path,
) -> int:
    """Invoke a brain script directly — robust to `core-` package naming.

    We pass --project-root and --db explicitly so the brain module doesn't
    rely on cwd-relative defaults.
    """
    if not script.exists():
        click.echo(f"ERROR: brain module not found: {script}", err=True)
        return 2
    env = os.environ.copy()
    # Ensure the brain's own dir is on sys.path so sibling modules import.
    env["PYTHONPATH"] = str(BRAIN_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        env=env,
        cwd=str(project),
    )
    return proc.returncode


@click.command("docs-index")
@click.option(
    "--project-dir", "-d", default=".",
    help="Project directory (default: current)",
)
@click.option(
    "--config", default=None,
    help="Path to rag-config.yaml (default: <project>/.coding-os/rag-config.yaml)",
)
@click.option(
    "--force", is_flag=True, default=False,
    help="Re-index every file regardless of mtime",
)
def docs_index(project_dir: str, config: str | None, force: bool) -> None:
    """Index project docs/ into thinking_os for RAG retrieval.

    This is the stable entry point that project Makefiles should call —
    it owns path discovery so no absolute paths need to be burned into
    per-project files.
    """
    project = _resolve_project_dir(project_dir)
    cfg_path = Path(config).resolve() if config else project / ".coding-os" / "rag-config.yaml"
    db_path = project / ".coding-os" / "coding-os.db"

    args = [
        "--config", str(cfg_path),
        "--project-root", str(project),
        "--db", str(db_path),
    ]
    if force:
        args.append("--force")

    rc = _run_brain_module(DOC_INDEXER, args, project=project)
    sys.exit(rc)


@click.command("task-sync")
@click.option(
    "--project-dir", "-d", default=".",
    help="Project directory (default: current)",
)
@click.option(
    "--force", is_flag=True, default=False,
    help="Re-sync every task file regardless of mtime",
)
def task_sync(project_dir: str, force: bool) -> None:
    """Sync docs/tasks/*.md into the thinking_os tasks table."""
    project = _resolve_project_dir(project_dir)
    db_path = project / ".coding-os" / "coding-os.db"

    args = [
        "--project-root", str(project),
        "--db", str(db_path),
    ]
    if force:
        args.append("--force")

    rc = _run_brain_module(TASK_SYNC, args, project=project)
    sys.exit(rc)


@click.command("reindex")
@click.option(
    "--project-dir", "-d", default=".",
    help="Project directory (default: current)",
)
def reindex(project_dir: str) -> None:
    """Re-embed all observations/patterns/outcomes after an embedding model change."""
    project = _resolve_project_dir(project_dir)
    db_path = project / ".coding-os" / "coding-os.db"

    rc = _run_brain_module(
        EMBEDDINGS,
        ["--reindex", "--db", str(db_path)],
        project=project,
    )
    sys.exit(rc)


@click.command("graph-reindex")
@click.option(
    "--project-dir", "-d", default=".",
    help="Project directory (default: current).",
)
@click.option(
    "--force", is_flag=True, default=False,
    help="Re-extract every file regardless of content hash.",
)
@click.option(
    "--file", "single_file", default=None,
    help="Reindex a single file (incremental; used by auto-reindex-graph.sh).",
)
@click.option(
    "--max-files", type=int, default=50_000,
    help="Safety cap on files walked.",
)
@click.option(
    "--quiet", is_flag=True, default=False,
    help="Suppress progress lines.",
)
def graph_reindex(
    project_dir: str,
    force: bool,
    single_file: str | None,
    max_files: int,
    quiet: bool,
) -> None:
    """Index the project into the graph_os knowledge graph.

    Bulk walk by default: walks the project, extracts Python / TS /
    markdown / YAML / shell / Go, and upserts nodes + edges into the
    shared SQLite DB.  Incremental via content-hash skipping, so re-runs
    are cheap.

    Use `--file <path>` for single-file incremental (the PostToolUse
    hook `auto-reindex-graph.sh` calls this path).
    """
    project = _resolve_project_dir(project_dir)
    db_path = project / ".coding-os" / "coding-os.db"

    args = [
        "--project-root", str(project),
        "--db", str(db_path),
        "--max-files", str(max_files),
    ]
    if force:
        args.append("--force")
    if single_file:
        args.extend(["--file", single_file])
    if quiet:
        args.append("--quiet")

    rc = _run_brain_module(GRAPH_INDEXER, args, project=project)
    sys.exit(rc)


@click.command("brain-decay")
@click.option(
    "--project-dir", "-d", default=".",
    help="Project directory (default: current)",
)
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Compute decay stats without writing.",
)
def brain_decay(project_dir: str, dry_run: bool) -> None:
    """Apply Ebbinghaus confidence decay to learned_patterns."""
    project = _resolve_project_dir(project_dir)
    args = ["--project-root", str(project)]
    if dry_run:
        args.append("--dry-run")
    rc = _run_brain_module(DECAY_SCRIPT, args, project=project)
    sys.exit(rc)


@click.command("brain-gc")
@click.option(
    "--project-dir", "-d", default=".",
    help="Project directory (default: current)",
)
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Report orphans without deleting.",
)
def brain_gc(project_dir: str, dry_run: bool) -> None:
    """Garbage-collect dangling memory rows."""
    project = _resolve_project_dir(project_dir)
    args = ["--project-root", str(project)]
    if dry_run:
        args.append("--dry-run")
    rc = _run_brain_module(GC_SCRIPT, args, project=project)
    sys.exit(rc)
