"""Graph OS end-to-end tests: file write → dispatch → backend → MCP query.

Each test owns the full observable pipeline so unit tests can stay narrow.
Coverage:
  - Python / TypeScript / Go / Markdown extraction → nodes+edges in DB
  - Prune-on-rename: old symbols disappear after file edit
  - Cache hit on unchanged file; force-bypass clears cache
  - MCP cos_graph_query finds extracted symbols
  - Go extractor is wired into dispatch (regression for the A5 gap)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[4]
_CORE = _REPO / "core"
for _p in [str(_CORE), str(_CORE / "thinking_os")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_setup(tmp_path):
    """Initialise a real SQLite DB at tmp_path/.coding-os/coding-os.db."""
    import database as thinking_os_db  # type: ignore

    db_file = tmp_path / ".coding-os" / "coding-os.db"
    db_file.parent.mkdir(parents=True)
    conn = thinking_os_db.init_db(str(db_file))
    yield tmp_path, db_file, conn
    conn.close()


def _dispatch(file_path: Path, tmp_path: Path, db_file: Path, *, force: bool = False) -> dict[str, Any]:
    from graph_os.tools.reindex_dispatch import dispatch

    return dispatch(
        file_path,
        project_root=tmp_path,
        db_path=str(db_file),
        include_docs=False,
        force=force,
    )


def _make_backend(db_file: Path):
    """Open a fresh SqliteBackend from db_file (post-dispatch snapshot)."""
    import database as thinking_os_db  # type: ignore
    from graph_os.backends.sqlite_backend import SqliteBackend

    conn = thinking_os_db.init_db(str(db_file))
    return SqliteBackend(conn=conn), conn


def _query_ok(backend, q: str) -> list[dict[str, Any]]:
    from graph_os.tools import graph as gtools

    prev = gtools._BACKEND_SINGLETON
    gtools._BACKEND_SINGLETON = backend
    try:
        env = gtools.cos_graph_query(q)
    finally:
        gtools._BACKEND_SINGLETON = prev
    if isinstance(env, str):
        import json
        env = json.loads(env)
    assert env.get("ok") is True, f"expected ok, got: {env}"
    return env["data"].get("results", [])


# ---------------------------------------------------------------------------
# Python pipeline
# ---------------------------------------------------------------------------


class TestPythonPipeline:
    def test_function_dispatched_and_queryable(self, db_setup):
        tmp_path, db_file, _ = db_setup
        src = tmp_path / "src" / "mymodule.py"
        src.parent.mkdir()
        src.write_text("def hello_world():\n    pass\n")

        result = _dispatch(src, tmp_path, db_file)

        assert result["status"] == "ok"
        assert result["layers"]["graph"]["nodes_written"] >= 1

        backend, conn = _make_backend(db_file)
        try:
            hits = _query_ok(backend, "hello_world")
            uids = [h.get("uid", "") for h in hits]
            assert any("hello_world" in u for u in uids), f"no hello_world in {uids}"
        finally:
            conn.close()

    def test_class_and_method_extracted(self, db_setup):
        tmp_path, db_file, _ = db_setup
        src = tmp_path / "models.py"
        src.write_text(
            "class UserModel:\n    def get_user(self, uid):\n        pass\n"
        )

        result = _dispatch(src, tmp_path, db_file)

        assert result["layers"]["graph"]["nodes_written"] >= 2

        backend, conn = _make_backend(db_file)
        try:
            hits = _query_ok(backend, "UserModel")
            assert any("UserModel" in h.get("uid", "") for h in hits)
        finally:
            conn.close()

    def test_prune_removes_renamed_function(self, db_setup):
        tmp_path, db_file, _ = db_setup
        src = tmp_path / "util.py"
        src.write_text("def old_function():\n    pass\n")
        _dispatch(src, tmp_path, db_file)

        # Rename — dispatch again with force so cache is bypassed
        src.write_text("def new_function():\n    pass\n")
        _dispatch(src, tmp_path, db_file, force=True)

        backend, conn = _make_backend(db_file)
        try:
            old_hits = _query_ok(backend, "old_function")
            assert not any("old_function" in h.get("uid", "") for h in old_hits), \
                "old_function should be pruned"
            new_hits = _query_ok(backend, "new_function")
            assert any("new_function" in h.get("uid", "") for h in new_hits)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TypeScript pipeline
# ---------------------------------------------------------------------------


class TestTypeScriptPipeline:
    def test_ts_function_dispatched(self, db_setup):
        tmp_path, db_file, _ = db_setup
        src = tmp_path / "src" / "api.ts"
        src.parent.mkdir()
        src.write_text(
            "export function fetchUser(id: string): Promise<User> {\n  return fetch(`/user/${id}`);\n}\n"
        )

        result = _dispatch(src, tmp_path, db_file)

        assert result["status"] == "ok"
        assert result["layers"]["graph"]["nodes_written"] >= 1

        backend, conn = _make_backend(db_file)
        try:
            hits = _query_ok(backend, "fetchUser")
            assert any("fetchUser" in h.get("uid", "") for h in hits)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Go pipeline (regression: code_go extractor was created but not wired)
# ---------------------------------------------------------------------------


class TestGoPipeline:
    def test_go_function_dispatched(self, db_setup):
        tmp_path, db_file, _ = db_setup
        src = tmp_path / "cmd" / "main.go"
        src.parent.mkdir()
        src.write_text(
            'package main\n\nimport "fmt"\n\nfunc main() {\n    fmt.Println("hello")\n}\n'
        )

        result = _dispatch(src, tmp_path, db_file)

        assert result["status"] == "ok"
        assert "graph" in result["layers"]
        assert result["layers"]["graph"]["nodes_written"] >= 1, \
            "code_go extractor must be wired (was broken before A5 fix)"

    def test_go_method_dispatched(self, db_setup):
        tmp_path, db_file, _ = db_setup
        src = tmp_path / "internal" / "server.go"
        src.parent.mkdir()
        src.write_text(
            "package server\n\ntype Server struct{}\n\n"
            "func (s *Server) Start() error {\n    return nil\n}\n"
        )

        result = _dispatch(src, tmp_path, db_file)

        assert result["layers"]["graph"]["nodes_written"] >= 2  # struct + method


# ---------------------------------------------------------------------------
# Markdown pipeline
# ---------------------------------------------------------------------------


class TestMarkdownPipeline:
    def test_md_link_edge_written(self, db_setup):
        tmp_path, db_file, _ = db_setup
        (tmp_path / "docs").mkdir()
        src = tmp_path / "docs" / "overview.md"
        src.write_text(
            "# Overview\n\nSee [architecture](architecture.md) for details.\n"
        )

        result = _dispatch(src, tmp_path, db_file)

        assert result["status"] == "ok"
        graph_layer = result["layers"].get("graph", {})
        assert graph_layer.get("edges_written", 0) >= 1

    def test_task_md_uses_task_deps_chain(self, db_setup):
        tmp_path, db_file, _ = db_setup
        (tmp_path / "docs" / "tasks").mkdir(parents=True)
        src = tmp_path / "docs" / "tasks" / "TASK-001-test.md"
        src.write_text(
            "---\ntask_id: TASK-001\ntitle: Test\nstatus: open\n---\n\nBody.\n"
        )

        result = _dispatch(src, tmp_path, db_file)

        assert result["status"] == "ok"
        assert "graph" in result["layers"]
        assert result["layers"]["graph"]["chain"] == "markdown-task"


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------


class TestCacheBehaviour:
    def test_first_dispatch_is_miss(self, db_setup):
        tmp_path, db_file, _ = db_setup
        src = tmp_path / "cache_test.py"
        src.write_text("def fn_a(): pass\n")

        result = _dispatch(src, tmp_path, db_file)

        assert result["cache"] == "miss"

    def test_second_dispatch_unchanged_is_hit(self, db_setup):
        tmp_path, db_file, _ = db_setup
        src = tmp_path / "stable.py"
        src.write_text("def stable_fn(): pass\n")
        _dispatch(src, tmp_path, db_file)

        r2 = _dispatch(src, tmp_path, db_file)

        assert r2["cache"] == "hit"

    def test_force_true_bypasses_cache(self, db_setup):
        tmp_path, db_file, _ = db_setup
        src = tmp_path / "forced.py"
        src.write_text("def forced_fn(): pass\n")
        _dispatch(src, tmp_path, db_file)

        r2 = _dispatch(src, tmp_path, db_file, force=True)

        assert r2["cache"] == "bypass"

    def test_modified_file_is_miss_not_hit(self, db_setup):
        tmp_path, db_file, _ = db_setup
        src = tmp_path / "evolving.py"
        src.write_text("def v1(): pass\n")
        _dispatch(src, tmp_path, db_file)

        src.write_text("def v2(): pass\n")
        r2 = _dispatch(src, tmp_path, db_file)

        assert r2["cache"] in {"miss", "partial"}


# ---------------------------------------------------------------------------
# Unsupported / edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_unsupported_extension_skipped(self, db_setup):
        tmp_path, db_file, _ = db_setup
        src = tmp_path / "binary.exe"
        src.write_bytes(b"\x00\x01\x02")

        result = _dispatch(src, tmp_path, db_file)

        assert result["status"] == "skipped"

    def test_missing_file_handled_gracefully(self, db_setup):
        tmp_path, db_file, _ = db_setup
        ghost = tmp_path / "does_not_exist.py"

        result = _dispatch(ghost, tmp_path, db_file)

        assert result["status"] in {"ok", "skipped", "error"}
        # Must not raise — dispatch is always safe
