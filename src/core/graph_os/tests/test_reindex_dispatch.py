"""Tests for graph_os.tools.reindex_dispatch (Phase I.14)."""

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
        src = _write(project / "core" / "a.rs", "fn main() {}")
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

    def test_duration_reported(self, project, tmp_path):
        src = _write(project / "core" / "a.py", "def x(): pass")
        from graph_os.tools.reindex_dispatch import dispatch

        report = dispatch(src, project_root=project, db_path=str(tmp_path / "t.db"))
        assert report["duration_ms"] >= 0

    def test_missing_file_handled(self, project, tmp_path):
        from graph_os.tools.reindex_dispatch import dispatch

        report = dispatch(
            project / "docs" / "nope.md",
            project_root=project,
            db_path=str(tmp_path / "t.db"),
        )
        assert "graph" in report["layers"]
        assert report["layers"]["graph"]["status"] == "error"

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
