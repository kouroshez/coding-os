"""Corpus ingestion: `cos graph-index-*` and `cos graph-detect-changes`."""

from __future__ import annotations

import tempfile
from pathlib import Path

import click

from cli._graph_cli_shared import (
    _bootstrap_paths,
    _json_echo,
    _open_backend,
)


def register_ingest(cli: click.Group) -> None:
    """Attach this slice of the `cos graph-*` family onto `cli`."""

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
        with click.progressbar(plan.files, label="[local] indexing") as bar:
            for file_path in bar:
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
        with click.progressbar(plan.files, label="[github] indexing") as bar:
            for file_path in bar:
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
        with click.progressbar(plan.files, label="[zip] indexing") as bar:
            for file_path in bar:
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
        """Map changed files to affected graph symbols + downstream tasks."""
        import subprocess

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
            files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except FileNotFoundError:
            raise click.ClickException("git not found on PATH") from None
        except subprocess.TimeoutExpired:
            raise click.ClickException("git diff timed out after 30 s") from None

        _, tools = _open_backend()
        _json_echo(
            tools.cos_graph_detect_changes(
                scope=scope,
                files=files or None,
                analyze_downstream=True,
            ),
            pretty=pretty,
        )
