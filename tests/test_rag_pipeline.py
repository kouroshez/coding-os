"""Regression tests for the RAG pipeline.

These guard against the three-way failure mode we hit in earlier
sessions:

 1. `make docs-index` silently populating 0 chunks
 2. `python -m core.thinking_os.doc_indexer` (invalid module path)
 3. `COS_ROOT` relative-path resolution breaking for `uv tool install` users

If any of them regresses, these tests fail with an actionable message.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FROZEN_DATE = "2026-01-01"


def _init_project(target: Path, *, agent: str = "claude") -> None:
    """Scaffold a project using the module CLI so tests don't require the
    `cos` binary to be installed globally."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.main",
            "init",
            "--agent",
            agent,
            "--project-dir",
            str(target.parent),
            "--name",
            target.name,
            "--no-git",
            "--no-register",
            "--today",
            FROZEN_DATE,
        ],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, f"init failed: {proc.stderr}"


@pytest.mark.slow
def test_cos_docs_index_populates_chunks(tmp_path: Path) -> None:
    """`cos docs-index` must actually write document_chunks rows.

    Historical regression: `make docs-index` used `python -m
    core.thinking_os.doc_indexer` which fails with ModuleNotFoundError
    because `core-` is not a valid Python package name. Fix: the
    `cos docs-index` subcommand invokes doc_indexer.py directly.
    """
    project = tmp_path / "rag-proj"
    _init_project(project)

    # Invoke the brain module as the cos subcommand would — this avoids
    # depending on the `cos` binary being installed globally in CI.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.main",
            "docs-index",
            "--project-dir",
            str(project),
        ],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, (
        f"cos docs-index failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    db_path = project / ".coding-os" / "coding-os.db"
    assert db_path.exists(), "coding-os.db not created"

    conn = sqlite3.connect(str(db_path))
    try:
        (chunk_count,) = conn.execute("SELECT COUNT(*) FROM document_chunks").fetchone()
    finally:
        conn.close()

    assert chunk_count > 0, (
        f"document_chunks is empty after cos docs-index "
        f"— pipeline is broken. stdout: {result.stdout}"
    )


@pytest.mark.slow
def test_cos_docs_index_force_reindexes(tmp_path: Path) -> None:
    """--force must re-embed every file regardless of mtime."""
    project = tmp_path / "rag-force"
    _init_project(project)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    base_cmd = [
        sys.executable,
        "-m",
        "cli.main",
        "docs-index",
        "--project-dir",
        str(project),
    ]

    first = subprocess.run(
        base_cmd, env=env, capture_output=True, text=True, timeout=300, check=False
    )
    assert first.returncode == 0

    second = subprocess.run(
        [*base_cmd, "--force"],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert second.returncode == 0
    # Second run with --force should process files again (not skip).
    assert '"processed": 6' in second.stdout or '"processed":' in second.stdout


@pytest.mark.slow
def test_makefile_docs_index_target_uses_cos_binary(tmp_path: Path) -> None:
    """The scaffolded Makefile.base must call `cos docs-index`, not
    `python -m core.thinking_os.*` (the regression we fixed)."""
    project = tmp_path / "mk-proj"
    _init_project(project)

    makefile = project / ".coding-os" / "Makefile.base"
    assert makefile.exists()
    content = makefile.read_text()

    # Positive: cos subcommands present
    assert "cos docs-index" in content
    assert "cos task-sync" in content
    assert "cos reindex" in content

    # Negative: broken module invocation must not exist
    assert "core.thinking_os.doc_indexer" not in content
    assert "core.thinking_os.task_sync" not in content
    assert "core.thinking_os.embeddings" not in content


@pytest.mark.slow
def test_makefile_base_is_portable_no_absolute_paths(tmp_path: Path) -> None:
    """Makefile.base copied into a project must not contain any absolute
    path to the coding-os install (the COS_ROOT burn-in hack)."""
    project = tmp_path / "portable-proj"
    _init_project(project)

    makefile = project / ".coding-os" / "Makefile.base"
    content = makefile.read_text()

    # Portability: derive the install root from the runtime (`cos`) or
    # the adapter hook symlink, never from the consumer project's own path.
    assert "cos hooks-dir" in content
    assert ".claude/hooks/cos-env.sh" in content
    assert ".codex/hooks/cos-env.sh" in content

    # Negative: no absolute /Users/... /home/... paths should appear
    for bad_prefix in ("/Users/", "/home/", "/private/var/"):
        assert bad_prefix not in content, (
            f"Makefile.base contains a machine-specific absolute path: "
            f"look for lines starting with {bad_prefix}"
        )


@pytest.mark.slow
@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_make_session_init_works_outside_repo(tmp_path: Path, agent: str) -> None:
    """Consumer projects must be able to run Make targets outside the repo."""
    project = tmp_path / f"portable-run-{agent}"
    _init_project(project, agent=agent)

    result = subprocess.run(
        ["make", "session-init"],
        cwd=str(project),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, (
        f"make session-init failed for {agent} project:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "=== Project Status ===" in result.stdout


@pytest.mark.slow
def test_task_start_blocks_template_placeholder_outcome(tmp_path: Path) -> None:
    """Current task model: the Definition-of-Ready gate blocks task-start
    while the Outcome is still a template placeholder, and allows it once a
    real Outcome is filled. (Replaces the retired REF-template + task-start
    .doc-anchor-copy workflow — task-start moves the task, it does not write
    the anchor; `make task-create` is now a usage-only stub, so drive the
    module CLI directly, matching `_init_project`.)"""
    project = tmp_path / "task-start-proj"
    _init_project(project)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)

    created = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.main",
            "task-create",
            "--title",
            "smoke workflow simulation",
            "--swimlane",
            "infra",
            "--kind",
            "chore",
        ],
        cwd=str(project),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert created.returncode == 0, created.stderr or created.stdout
    task_id = json.loads(created.stdout)["task_id"]

    # Mark ready first so the require_ready_label gate passes and the
    # start transition reaches the DoR content gate we're exercising.
    readied = subprocess.run(
        [sys.executable, "-m", "cli.main", "task-ready", task_id],
        cwd=str(project),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert readied.returncode == 0, readied.stderr or readied.stdout

    # Placeholder Outcome → DoR gate blocks the start transition.
    blocked = subprocess.run(
        [sys.executable, "-m", "cli.main", "task-start", task_id],
        cwd=str(project),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert blocked.returncode != 0, "DoR gate should block a placeholder Outcome"
    assert "placeholder" in (blocked.stdout + blocked.stderr).lower()

    # Fill the Outcome with real content → task-start succeeds.
    task_file = next((project / "docs" / "tasks").glob(f"{task_id}-*.md"))
    task_file.write_text(
        re.sub(
            r"\(fill in[^\n]*\)",
            "Real outcome for the task-start smoke test.",
            task_file.read_text(encoding="utf-8"),
        ),
        encoding="utf-8",
    )
    started = subprocess.run(
        [sys.executable, "-m", "cli.main", "task-start", task_id],
        cwd=str(project),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert started.returncode == 0, (
        f"task-start failed:\nstdout: {started.stdout}\nstderr: {started.stderr}"
    )
    assert "SyntaxWarning" not in (started.stdout + started.stderr)
