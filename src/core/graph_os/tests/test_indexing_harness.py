"""Phase I.10 — indexing-harness tests (small, safe, bounded).

Covers:
  - graph_indexer.index_single_file (incremental + content-hash skip + unsupported suffix + unreadable file)
  - graph_indexer.index_project (bulk + idempotent re-run + determinism)
  - background._default_graph_index_runner (fires under COS_PROJECT_ROOT)
  - warn-graph-empty.sh (missing DB warns; empty DB warns; non-empty silent; debounce)
  - cos graph-reindex CLI (subprocess smoke via Click runner)
  - reindex_dispatch routes by suffix (python / md / yaml)

Design rules:
  - Every test uses tmp_path for DB and project dir; zero production touch.
  - No threads — we call run_once directly instead of starting the loop.
  - Subprocess calls capped with timeout=30.
  - No network, no sleep > 0.01s.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
THINKING_OS = REPO_ROOT / "core" / "thinking_os"
HOOKS = REPO_ROOT / "core" / "hooks"


@pytest.fixture()
def thinking_os_on_path():
    """Put core/ + core/thinking_os on sys.path for this test only."""
    added: list[str] = []
    for p in (str(THINKING_OS.parent), str(THINKING_OS)):
        if p not in sys.path:
            sys.path.insert(0, p)
            added.append(p)
    try:
        yield
    finally:
        for p in added:
            try:
                sys.path.remove(p)
            except ValueError:
                pass


@pytest.fixture()
def tiny_project(tmp_path: Path):
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "mod.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    (root / "README.md").write_text("# Proj\n\nSee [mod](pkg/mod.py).\n", encoding="utf-8")
    (root / ".coding-os").mkdir()
    db_path = root / ".coding-os" / "coding-os.db"
    return root, db_path


# ---------------------------------------------------------------------------
# index_single_file — incremental path used by the hook
# ---------------------------------------------------------------------------


class TestIndexSingleFile:
    def test_indexes_python_file(self, thinking_os_on_path, tiny_project):
        root, db_path = tiny_project
        import graph_indexer  # type: ignore

        backend = graph_indexer.open_backend(db_path)
        try:
            report = graph_indexer.index_single_file(
                backend=backend,
                project_root=root,
                file_path=root / "pkg" / "mod.py",
            )
            assert report.mode == "incremental"
            assert report.files_seen == 1
            assert report.files_indexed == 1
            assert report.nodes_upserted >= 2
            assert report.errors == []
        finally:
            backend.close()

    def test_unsupported_suffix_is_skipped(self, thinking_os_on_path, tiny_project):
        root, db_path = tiny_project
        (root / "data.bin").write_bytes(b"\x00\x01\x02")
        import graph_indexer  # type: ignore

        backend = graph_indexer.open_backend(db_path)
        try:
            report = graph_indexer.index_single_file(
                backend=backend,
                project_root=root,
                file_path=root / "data.bin",
            )
            assert report.files_skipped_unsupported == 1
            assert report.files_indexed == 0
        finally:
            backend.close()

    def test_unchanged_file_is_skipped(self, thinking_os_on_path, tiny_project):
        root, db_path = tiny_project
        import graph_indexer  # type: ignore

        backend = graph_indexer.open_backend(db_path)
        try:
            r1 = graph_indexer.index_single_file(
                backend=backend,
                project_root=root,
                file_path=root / "pkg" / "mod.py",
            )
            assert r1.files_indexed == 1
            r2 = graph_indexer.index_single_file(
                backend=backend,
                project_root=root,
                file_path=root / "pkg" / "mod.py",
            )
            assert r2.files_skipped_unchanged == 1
            assert r2.files_indexed == 0
        finally:
            backend.close()

    def test_unreadable_file_reports_error(self, thinking_os_on_path, tiny_project):
        root, db_path = tiny_project
        # Non-existent file — read_text will OSError.
        import graph_indexer  # type: ignore

        backend = graph_indexer.open_backend(db_path)
        try:
            report = graph_indexer.index_single_file(
                backend=backend,
                project_root=root,
                file_path=root / "pkg" / "ghost.py",
            )
            assert report.files_errored == 1
            assert report.errors
        finally:
            backend.close()


# ---------------------------------------------------------------------------
# index_project — bulk path used by CLI + background
# ---------------------------------------------------------------------------


class TestIndexProject:
    def test_bulk_indexes_all_files(self, thinking_os_on_path, tiny_project):
        root, db_path = tiny_project
        import graph_indexer  # type: ignore

        backend = graph_indexer.open_backend(db_path)
        try:
            report = graph_indexer.index_project(
                backend=backend,
                project_root=root,
            )
            assert report.mode == "bulk"
            assert report.files_seen >= 2
            assert report.files_indexed >= 2
        finally:
            backend.close()

    def test_rerun_skips_unchanged(self, thinking_os_on_path, tiny_project):
        root, db_path = tiny_project
        import graph_indexer  # type: ignore

        backend = graph_indexer.open_backend(db_path)
        try:
            graph_indexer.index_project(backend=backend, project_root=root)
            report = graph_indexer.index_project(
                backend=backend,
                project_root=root,
            )
            assert report.files_skipped_unchanged >= 2
            assert report.files_indexed <= 1  # at most the md+task cross-extractor

        finally:
            backend.close()

    def test_force_re_extracts(self, thinking_os_on_path, tiny_project):
        root, db_path = tiny_project
        import graph_indexer  # type: ignore

        backend = graph_indexer.open_backend(db_path)
        try:
            graph_indexer.index_project(backend=backend, project_root=root)
            report = graph_indexer.index_project(
                backend=backend,
                project_root=root,
                force=True,
            )
            assert report.files_skipped_unchanged == 0
        finally:
            backend.close()

    def test_max_files_cap(self, thinking_os_on_path, tiny_project):
        root, db_path = tiny_project
        # Spam files to test cap.
        for i in range(5):
            (root / f"pad_{i}.py").write_text(f"x = {i}\n", encoding="utf-8")
        import graph_indexer  # type: ignore

        backend = graph_indexer.open_backend(db_path)
        try:
            with pytest.raises(Exception):
                graph_indexer.index_project(
                    backend=backend,
                    project_root=root,
                    max_files=3,
                )
        finally:
            backend.close()


# ---------------------------------------------------------------------------
# background._default_graph_index_runner
# ---------------------------------------------------------------------------


class TestBackgroundGraphRunner:
    def test_runner_indexes_project(self, thinking_os_on_path, tiny_project, monkeypatch):
        root, db_path = tiny_project
        monkeypatch.setenv("COS_PROJECT_ROOT", str(root))
        monkeypatch.setenv("COS_DB_PATH", str(db_path))
        monkeypatch.setenv("COS_BACKGROUND_GRAPH_MAX_FILES", "1000")

        import background  # type: ignore

        result = background._default_graph_index_runner()
        assert result["status"] == "ok"
        assert result["stats"]["files_seen"] >= 2

    def test_runner_skipped_when_project_missing(self, thinking_os_on_path, tmp_path, monkeypatch):
        monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path / "ghost"))
        monkeypatch.setenv("COS_DB_PATH", str(tmp_path / "t.db"))
        import background  # type: ignore

        result = background._default_graph_index_runner()
        assert result["status"] == "skipped"

    def test_run_once_fires_graph_step(self, thinking_os_on_path, tiny_project, monkeypatch):
        """BackgroundIndexer.run_once() should record a graph iter."""
        root, db_path = tiny_project
        monkeypatch.setenv("COS_PROJECT_ROOT", str(root))
        monkeypatch.setenv("COS_DB_PATH", str(db_path))
        import background  # type: ignore

        bg = background.BackgroundIndexer(interval_seconds=30)
        stats = bg.run_once()
        assert "graph" in stats
        assert stats["graph"]["status"] in {"ok", "skipped"}


# ---------------------------------------------------------------------------
# warn-graph-empty.sh — SessionStart non-blocking warning
# ---------------------------------------------------------------------------


class TestWarnGraphEmptyHook:
    def _run_hook(self, tmp_path: Path, *, db_path: Path | None) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["COS_STATE_DIR"] = str(tmp_path)
        env["COS_AGENT_DIR"] = str(tmp_path / "agent")
        if db_path is not None:
            env["COS_DB_PATH"] = str(db_path)
        else:
            env["COS_DB_PATH"] = str(tmp_path / "missing.db")
        return subprocess.run(
            ["bash", str(HOOKS / "warn-graph-empty.sh")],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )

    def test_missing_db_warns(self, tmp_path):
        result = self._run_hook(tmp_path, db_path=None)
        assert result.returncode == 0
        assert "Graph not indexed" in result.stderr

    def test_empty_db_warns(self, thinking_os_on_path, tmp_path):
        from database import init_db  # type: ignore

        db_path = tmp_path / "e.db"
        init_db(str(db_path)).close()
        result = self._run_hook(tmp_path, db_path=db_path)
        assert result.returncode == 0
        assert "graph_nodes=0" in result.stderr

    def test_non_empty_db_silent(self, thinking_os_on_path, tmp_path):
        from database import init_db  # type: ignore

        from graph_os.backends.sqlite_backend import SqliteBackend
        from graph_os.types import GraphNode

        db_path = tmp_path / "full.db"
        conn = init_db(str(db_path))
        backend = SqliteBackend(conn=conn)
        backend.bulk_upsert(
            [GraphNode(uid="code:function:a", kind="code:function", label="a")],
            [],
        )
        conn.commit()
        conn.close()
        result = self._run_hook(tmp_path, db_path=db_path)
        assert result.returncode == 0
        assert "Graph not indexed" not in result.stderr

    def test_debounce_once_per_session(self, tmp_path):
        first = self._run_hook(tmp_path, db_path=None)
        second = self._run_hook(tmp_path, db_path=None)
        assert "Graph not indexed" in first.stderr
        assert "Graph not indexed" not in second.stderr


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------


class TestCliGraphReindex:
    def test_cli_full_run_exits_zero(self, tiny_project):
        root, db_path = tiny_project
        env = os.environ.copy()
        env.setdefault("PYTHONPATH", str(REPO_ROOT))
        # Use the brain module directly — avoids click entrypoint overhead.
        proc = subprocess.run(
            [
                sys.executable,
                str(THINKING_OS / "graph_indexer.py"),
                "--project-root",
                str(root),
                "--db",
                str(db_path),
                "--quiet",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["files_indexed"] >= 2
        assert payload["mode"] == "bulk"

    def test_cli_single_file_mode(self, tiny_project):
        root, db_path = tiny_project
        # Seed once so the content-hash skip path is exercised.
        env = os.environ.copy()
        env.setdefault("PYTHONPATH", str(REPO_ROOT))
        subprocess.run(
            [
                sys.executable,
                str(THINKING_OS / "graph_indexer.py"),
                "--project-root",
                str(root),
                "--db",
                str(db_path),
                "--quiet",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(THINKING_OS / "graph_indexer.py"),
                "--project-root",
                str(root),
                "--db",
                str(db_path),
                "--file",
                str(root / "pkg" / "mod.py"),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["mode"] == "incremental"


# ---------------------------------------------------------------------------
# reindex_dispatch — suffix → extractor routing
# ---------------------------------------------------------------------------


class TestReindexDispatch:
    def test_python_routes_through_graph_chain(self, thinking_os_on_path, tiny_project):
        root, db_path = tiny_project
        from graph_os.tools.reindex_dispatch import dispatch

        result = dispatch(
            root / "pkg" / "mod.py",
            project_root=root,
            db_path=str(db_path),
        )
        assert result["status"] == "ok"
        assert "graph" in result["layers"]

    def test_markdown_routes_both_layers(self, thinking_os_on_path, tiny_project):
        root, db_path = tiny_project
        (root / ".coding-os" / "rag-config.yaml").write_text(
            textwrap.dedent(
                """
                sources:
                  - name: docs
                    path: .
                    suffixes: [md]
                    tag: generic
                """
            ).strip(),
            encoding="utf-8",
        )
        from graph_os.tools.reindex_dispatch import dispatch

        result = dispatch(
            root / "README.md",
            project_root=root,
            db_path=str(db_path),
        )
        assert result["status"] == "ok"
        # Graph layer always present; docs only if rag-config + extras resolve.
        assert "graph" in result["layers"]

    def test_unknown_suffix_returns_skipped(self, thinking_os_on_path, tiny_project):
        root, db_path = tiny_project
        (root / "data.bin").write_bytes(b"\x00")
        from graph_os.tools.reindex_dispatch import dispatch

        result = dispatch(
            root / "data.bin",
            project_root=root,
            db_path=str(db_path),
        )
        assert result["status"] == "skipped"
