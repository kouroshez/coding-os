"""Tests for graph_os.tools.reindex_dispatch."""

from __future__ import annotations

from pathlib import Path

import pytest


def _write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _edge_types_between(db: str, source_file: str, target_uid: str) -> set[str]:
    import sqlite3

    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT e.edge_type FROM graph_edges_v12 e "
            "JOIN graph_nodes s ON s.id = e.source_id "
            "JOIN graph_nodes t ON t.id = e.target_id "
            "WHERE t.uid = ? AND s.file_path = ?",
            (target_uid, source_file),
        ).fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


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
        # D7-F1: reindex on a path whose file was deleted must PRUNE
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

    def test_reindexing_callee_keeps_inbound_cross_file_edges(self, project, tmp_path):
        # An edit to util.py must not erase what caller.py says about it:
        # the next agent asking "who calls helper?" would get zero.
        from graph_os.tools.reindex_dispatch import dispatch

        db = str(tmp_path / "keep.db")
        callee = _write(project / "core" / "util.py", "def helper():\n    return 1\n")
        dispatch(callee, project_root=project, db_path=db)
        _write(
            project / "core" / "caller.py",
            "from core.util import helper\n\n\ndef go():\n    return helper()\n",
        )
        dispatch(project / "core" / "caller.py", project_root=project, db_path=db)
        assert _edge_types_between(db, "core/caller.py", "code:function:core/util.py::helper") == {
            "calls",
            "imports",
        }

        _write(callee, "def helper():\n    return 2\n\n\ndef unrelated():\n    return 3\n")
        dispatch(callee, project_root=project, db_path=db)

        assert _edge_types_between(db, "core/caller.py", "code:function:core/util.py::helper") == {
            "calls",
            "imports",
        }

    def test_reindex_drops_edges_the_file_no_longer_emits(self, project, tmp_path):
        from graph_os.tools.reindex_dispatch import dispatch

        db = str(tmp_path / "drop.db")
        dispatch(
            _write(project / "core" / "util.py", "def helper():\n    return 1\n"),
            project_root=project,
            db_path=db,
        )
        caller = _write(
            project / "core" / "caller.py",
            "from core.util import helper\n\n\ndef go():\n    return helper()\n",
        )
        dispatch(caller, project_root=project, db_path=db)

        _write(caller, "def go():\n    return 1\n")
        dispatch(caller, project_root=project, db_path=db)

        assert (
            _edge_types_between(db, "core/caller.py", "code:function:core/util.py::helper") == set()
        )

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
        # .rs is now routed to code_generic; use a suffix with no
        # _EXT_MAP route to assert the skip path.
        src = _write(project / "core" / "a.xyz", "nonsense")
        from graph_os.tools.reindex_dispatch import dispatch

        report = dispatch(src, project_root=project, db_path=str(tmp_path / "t.db"))
        assert report["status"] == "skipped"

    def test_render_dir_excluded(self, project, tmp_path):
        # the per-file path must skip render/dependency dirs the
        # bulk walker already excludes — otherwise it indexes a phenotype
        # COPY of a canonical src/ doc whose relative links mint broken stubs.
        src = _write(
            project / ".claude" / "rules" / "meta-hook-author.md",
            "# copy\n[reg](../../../core/hooks/registry.yaml)\n",
        )
        from graph_os.tools.reindex_dispatch import dispatch

        report = dispatch(src, project_root=project, db_path=str(tmp_path / "t.db"))
        assert report["status"] == "skipped"
        assert report["reason"] == "excluded-dir"

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

    def test_stale_graph_chain_self_heals(self, project, tmp_path):
        # when a file's routing changes (task_deps,md_links → md_links),
        # recording the new graph chain drops the stale one but keeps docs:md.
        import sqlite3

        from graph_os.tools.reindex_dispatch import _record_state_safe

        db = str(tmp_path / "t.db")
        rel = "docs/engineering/sample-note.md"
        common = {
            "content_hash": "h",
            "nodes_written": 0,
            "edges_written": 0,
            "last_error": None,
            "project_root": project,
            "db_path": db,
            "advance_hash": True,
        }
        # old graph chain with a stale parse error + the legit docs row
        _record_state_safe(rel, chain_key="task_deps,md_links", parse_errors_count=1, **common)
        _record_state_safe(rel, chain_key="docs:md", parse_errors_count=0, **common)
        # new graph chain — must evict the stale graph row, keep docs:md
        _record_state_safe(rel, chain_key="md_links", parse_errors_count=0, **common)

        con = sqlite3.connect(db)
        chains = {
            r[0]
            for r in con.execute(
                "SELECT extractor_chain FROM file_index_state WHERE file_path=?", (rel,)
            ).fetchall()
        }
        assert chains == {"md_links", "docs:md"}
        total_pe = con.execute(
            "SELECT COALESCE(SUM(parse_errors_count),0) FROM file_index_state WHERE file_path=?",
            (rel,),
        ).fetchone()[0]
        assert total_pe == 0  # the stale parse error is gone

    def test_rust_routes_to_code_generic(self, project, tmp_path):
        # a.rs file is dispatched through code_generic and yields
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
        # D7-F1: a path that doesn't exist on disk is a deletion, not
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

    def test_task_path_non_task_is_false(self):
        from graph_os.tools.reindex_dispatch import _is_task_path

        assert not _is_task_path("src/core/foo.py")

    def test_task_path_env_override(self, monkeypatch):
        from graph_os.tools.reindex_dispatch import _is_task_path

        monkeypatch.setenv("COS_TASK_PATH_FRAGMENTS", "tickets/")
        assert _is_task_path("docs/tickets/T-1.md")
        # Default fragments no longer apply once overridden.
        assert not _is_task_path("docs/tasks/TASK-1.md")


class TestDurationPersisted:
    def test_duration_ms_lands_in_file_index_state(self, project, tmp_path):
        # Polyglot roadmap E1.1 (migration v28): the per-file timing must be
        # PERSISTED, not just reported — cos_graph_doctor's
        # slowest_extractions category reads it back from the DB.
        import sqlite3

        src = _write(project / "core" / "timed.py", "def t(): pass")
        from graph_os.tools.reindex_dispatch import dispatch

        db = str(tmp_path / "t.db")
        dispatch(src, project_root=project, db_path=db)

        conn = sqlite3.connect(db)
        try:
            row = conn.execute(
                "SELECT duration_ms FROM file_index_state "
                "WHERE file_path LIKE '%timed.py' AND duration_ms IS NOT NULL"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None and int(row[0]) >= 0
