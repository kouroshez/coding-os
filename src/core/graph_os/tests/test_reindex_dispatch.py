"""Tests for graph_os.tools.reindex_dispatch."""

from __future__ import annotations

from pathlib import Path

import pytest


def _write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture()
def project(tmp_path):
    (tmp_path / ".coding-os").mkdir()
    (tmp_path / ".coding-os" / "rag-config.yaml").write_text(
        "sources:\n  docs:\n    - glob: 'docs/**/*.md'\n      category: docs\n",
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "core").mkdir()
    return tmp_path


class TestDispatch:
    def test_python_routes_to_graph(self, project, tmp_path):
        src = _write(
            project / "core" / "foo.py",
            "def hello(x):\n    return x\n",
        )
        from graph_os.tools.reindex_dispatch import dispatch

        db = tmp_path / "test.db"
        report = dispatch(src, project_root=project, db_path=str(db))
        assert report["status"] == "ok"
        assert "graph" in report["layers"]
        assert report["layers"]["graph"]["status"] == "ok"

    def test_read_error_on_deleted_file_prunes_graph(self, project, tmp_path):
        # D7-F1 (TASK-129): reindex on a path whose file was deleted must PRUNE
        # its graph nodes, not short-circuit on read_error — else deleted files
        # leave orphan nodes.
        import sqlite3

        from graph_os.tools.reindex_dispatch import dispatch

        db = str(tmp_path / "del.db")
        src = _write(project / "core" / "gone.py", "def doomed():\n    return 1\n")
        dispatch(src, project_root=project, db_path=db)

        def node_count() -> int:
            c = sqlite3.connect(db)
            try:
                return c.execute(
                    "SELECT COUNT(*) FROM graph_nodes WHERE file_path=?", ("core/gone.py",)
                ).fetchone()[0]
            finally:
                c.close()

        assert node_count() > 0  # indexed
        src.unlink()  # delete the file on disk
        report = dispatch(src, project_root=project, db_path=db)
        assert report["layers"]["graph"]["status"] == "pruned"
        assert node_count() == 0  # orphans pruned

    def test_read_error_on_existing_file_keeps_nodes(self, project, tmp_path):
        # A transient read error on a path that STILL EXISTS must NOT prune.
        import sqlite3

        from graph_os.tools.reindex_dispatch import dispatch

        db = str(tmp_path / "tr.db")
        src = project / "core" / "keep.py"
        _write(src, "def keeper():\n    return 1\n")
        dispatch(src, project_root=project, db_path=db)

        def node_count() -> int:
            c = sqlite3.connect(db)
            try:
                return c.execute(
                    "SELECT COUNT(*) FROM graph_nodes WHERE file_path=?", ("core/keep.py",)
                ).fetchone()[0]
            finally:
                c.close()

        assert node_count() > 0
        src.write_bytes(b"\xff\xfe invalid \x80 utf8")  # exists, but unreadable as utf-8
        report = dispatch(src, project_root=project, db_path=db)
        assert report["layers"]["graph"]["status"] == "error"
        assert node_count() > 0  # NOT pruned — file still exists

    def test_link_stubs_false_defers_to_global_pass(self, project, tmp_path):
        """TASK-043: link_stubs=False leaves a cross-file stub unresolved per
        file (a later file's prune would otherwise orphan a premature
        resolution); a single global link_external_stubs() then resolves it."""
        import sqlite3

        from graph_os.tools.reindex_dispatch import dispatch

        db = str(tmp_path / "t.db")
        _write(project / "core" / "util.py", "def helper():\n    return 1\n")
        dispatch(project / "core" / "util.py", project_root=project, db_path=db)
        _write(
            project / "core" / "caller.py",
            "from core.util import helper\n\n\ndef go():\n    return helper()\n",
        )
        dispatch(
            project / "core" / "caller.py",
            project_root=project,
            db_path=db,
            link_stubs=False,
        )

        def inbound():
            c = sqlite3.connect(db)
            try:
                row = c.execute(
                    "SELECT id FROM graph_nodes WHERE uid=?",
                    ("code:function:core/util.py::helper",),
                ).fetchone()
                return c.execute(
                    "SELECT COUNT(*) FROM graph_edges_v12 WHERE target_id=? AND edge_type='calls'",
                    (row[0],),
                ).fetchone()[0]
            finally:
                c.close()

        assert inbound() == 0  # deferred — not linked per-file
        from database import init_db  # type: ignore

        from graph_os.backends.sqlite_backend import SqliteBackend  # type: ignore

        SqliteBackend(conn=init_db(db)).link_external_stubs()
        assert inbound() == 1  # global pass resolved the cross-file call

    def test_ts_routes_to_graph(self, project, tmp_path):
        src = _write(
            project / "core" / "x.ts",
            "export function hi() { return 1; }",
        )
        from graph_os.tools.reindex_dispatch import dispatch

        db = tmp_path / "test.db"
        report = dispatch(src, project_root=project, db_path=str(db))
        assert report["layers"]["graph"]["status"] == "ok"

    def test_shell_routes_to_graph(self, project, tmp_path):
        src = _write(
            project / "core" / "hooks" / "x.sh",
            "#!/usr/bin/env bash\nsource ./util.sh\n",
        )
        from graph_os.tools.reindex_dispatch import dispatch

        report = dispatch(src, project_root=project, db_path=str(tmp_path / "t.db"))
        assert report["layers"]["graph"]["status"] == "ok"

    def test_yaml_routes_to_graph(self, project, tmp_path):
        src = _write(
            project / "core" / "conf.yaml",
            "key: value\nnested:\n  inner: x\n",
        )
        from graph_os.tools.reindex_dispatch import dispatch

        report = dispatch(src, project_root=project, db_path=str(tmp_path / "t.db"))
        assert report["layers"]["graph"]["status"] == "ok"

    def test_markdown_routes_to_both(self, project, tmp_path):
        src = _write(
            project / "docs" / "a.md",
            "# hello\n\nSee [b](./b.md).\n",
        )
        from graph_os.tools.reindex_dispatch import dispatch

        report = dispatch(src, project_root=project, db_path=str(tmp_path / "t.db"))
        assert "graph" in report["layers"]
        # docs layer may be `unscoped` when no chunks match, or `ok` when
        # the doc is in-scope — either is acceptable.

    def test_unsupported_suffix_skipped(self, project, tmp_path):
        # .rs is now routed to code_generic (TASK-296); use a suffix with no
        # _EXT_MAP route to assert the skip path.
        src = _write(project / "core" / "a.xyz", "nonsense")
        from graph_os.tools.reindex_dispatch import dispatch

        report = dispatch(src, project_root=project, db_path=str(tmp_path / "t.db"))
        assert report["status"] == "skipped"

    def test_task_markdown_uses_task_chain(self, project, tmp_path):
        src = _write(
            project / "docs" / "tasks" / "TASK-001-demo.md",
            (
                "<!-- domain:BACKEND | layer:task | ssot:true -->\n"
                "# TASK-001: [BACKEND] Demo\n\n"
                "## Goal\n\nShow the pipeline.\n\n"
                "## Source of Truth\n\n- docs/demo.md\n\n"
                "## Dependencies\n\n- TASK-002\n"
            ),
        )
        from graph_os.tools.reindex_dispatch import dispatch

        report = dispatch(src, project_root=project, db_path=str(tmp_path / "t.db"))
        assert report["layers"]["graph"]["chain"].startswith("markdown-task")

    def test_rust_routes_to_code_generic(self, project, tmp_path):
        # TASK-296: a .rs file is dispatched through code_generic and yields
        # real nodes (proves _EXT_MAP route + extractor_map wiring).
        import pytest

        pytest.importorskip("tree_sitter_rust")
        src = _write(project / "core" / "lib.rs", "struct P { x: i32 }\nfn main() {}\n")
        from graph_os.tools.reindex_dispatch import dispatch

        report = dispatch(src, project_root=project, db_path=str(tmp_path / "t.db"))
        graph = report["layers"]["graph"]
        assert graph["chain"].startswith("rust")
        assert int(graph["nodes_written"]) > 0

    def test_duration_reported(self, project, tmp_path):
        src = _write(project / "core" / "a.py", "def x(): pass")
        from graph_os.tools.reindex_dispatch import dispatch

        report = dispatch(src, project_root=project, db_path=str(tmp_path / "t.db"))
        assert report["duration_ms"] >= 0

    def test_missing_file_handled(self, project, tmp_path):
        # D7-F1 (TASK-129): a path that doesn't exist on disk is a deletion, not
        # an error — dispatch prunes (0 nodes for a never-indexed path) rather
        # than returning status=error, so reindexing a since-deleted path is
        # self-healing.
        from graph_os.tools.reindex_dispatch import dispatch

        report = dispatch(
            project / "docs" / "nope.md",
            project_root=project,
            db_path=str(tmp_path / "t.db"),
        )
        assert "graph" in report["layers"]
        assert report["layers"]["graph"]["status"] == "pruned"
        assert report["layers"]["graph"]["nodes_pruned"] == 0

    def test_include_docs_false_skips_rag(self, project, tmp_path):
        src = _write(project / "docs" / "x.md", "# hi\n")
        from graph_os.tools.reindex_dispatch import dispatch

        report = dispatch(
            src,
            project_root=project,
            db_path=str(tmp_path / "t.db"),
            include_docs=False,
        )
        assert "docs" not in report["layers"]
        assert "graph" in report["layers"]


class TestPureHelpers:
    def test_retryable_lock_error(self):
        from graph_os.tools.reindex_dispatch import _is_retryable_lock_error

        assert _is_retryable_lock_error(Exception("database is locked"))
        assert _is_retryable_lock_error(Exception("database is busy"))
        assert not _is_retryable_lock_error(Exception("syntax error near"))

    def test_task_path_matches_tasks_dir(self):
        from graph_os.tools.reindex_dispatch import _is_task_path

        assert _is_task_path("docs/tasks/TASK-001.md")
        assert _is_task_path("repo/tasks/ticket.md")

    def test_task_path_excludes_audits(self):
        from graph_os.tools.reindex_dispatch import _is_task_path

        # Audit artifacts live under docs/tasks/audits/ — NOT task files.
        assert not _is_task_path("docs/tasks/audits/audit-x.md")

    def test_task_path_non_task_is_false(self):
        from graph_os.tools.reindex_dispatch import _is_task_path

        assert not _is_task_path("src/core/foo.py")

    def test_task_path_env_override(self, monkeypatch):
        from graph_os.tools.reindex_dispatch import _is_task_path

        monkeypatch.setenv("COS_TASK_PATH_FRAGMENTS", "tickets/")
        assert _is_task_path("docs/tickets/T-1.md")
        # Default fragments no longer apply once overridden.
        assert not _is_task_path("docs/tasks/TASK-1.md")
