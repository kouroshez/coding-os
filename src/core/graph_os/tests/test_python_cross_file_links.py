"""Python attribute calls, module attributes, relative imports and module edges resolve to the right target."""

from __future__ import annotations

import sqlite3
import textwrap
from pathlib import Path

import pytest

from graph_os.extractors import code_python
from graph_os.extractors._python_uids import _absolute_module_for


def _targets(source: str, edge_type: str, path: str = "app/x.py") -> set[str]:
    result = code_python.extract(path, textwrap.dedent(source))
    return {edge.target_uid for edge in result.edges if edge.edge_type == edge_type}


def test_an_attribute_call_never_binds_to_a_same_file_name_by_its_last_segment():
    calls = _targets(
        """
        import requests

        class Repo:
            def get(self, key):
                return key

        def helper():
            requests.get("u")
            Repo.get(None, 1)
        """,
        "calls",
    )
    assert "code:external:requests:get" in calls
    assert "code:method:app/x.py::Repo.get" in calls
    assert calls.isdisjoint({"code:function:app/x.py::get"})


def test_a_module_qualified_base_class_keeps_its_attribute():
    bases = _targets(
        "import pydantic\n\nclass Model(pydantic.BaseModel):\n    pass\n", "inherits_from"
    )
    assert bases == {"code:external:pydantic:BaseModel"}


def test_a_dotted_import_resolves_to_the_longest_imported_module():
    calls = _targets(
        "import os.path\n\ndef f():\n    os.path.join('a')\n    os.getcwd()\n", "calls"
    )
    assert {"code:external:os.path:join", "code:external:os:getcwd"} <= calls


def test_a_relative_import_inside_a_package_init_stays_in_the_package():
    assert _absolute_module_for(".impl", path="app/pkg/__init__.py") == "app.pkg.impl"
    assert _absolute_module_for(".impl", path="app/pkg/mod.py") == "app.pkg.impl"


FILES = {
    "app/__init__.py": "",
    "app/types.py": "X = 1\n",
    "app/sibling.py": "def go():\n    return 1\n",
    "app/pkg/__init__.py": "from .impl import f\nfrom .facade import compute\n",
    "app/pkg/impl.py": "def f():\n    return 2\n",
    "app/pkg/facade.py": "from .core import compute\n",
    "app/pkg/core.py": "def compute():\n    return 4\n",
    "app/pkg/mod.py": "def thing():\n    return 3\n",
    "app/main.py": (
        "import types\n"
        "from . import sibling\n"
        "from .pkg.mod import thing\n"
        "from .pkg import compute\n"
        "\n\n"
        "def run():\n"
        "    thing()\n"
        "    sibling.go()\n"
        "    compute()\n"
    ),
}


@pytest.fixture()
def graph(tmp_path: Path) -> str:
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools.reindex_dispatch import dispatch

    (tmp_path / ".coding-os").mkdir()
    for relative, text in FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    db = str(tmp_path / "graph.db")
    for relative in FILES:
        dispatch(tmp_path / relative, project_root=tmp_path, db_path=db, include_docs=False)
    SqliteBackend(conn=init_db(db)).link_cross_file()
    return db


def _edges_from(db: str, source_file: str) -> set[tuple[str, str]]:
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT e.edge_type, t.uid FROM graph_edges_v12 e "
            "JOIN graph_nodes s ON s.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id "
            "WHERE s.file_path = ?",
            (source_file,),
        ).fetchall()
    finally:
        conn.close()
    return {tuple(row) for row in rows}


def test_relative_module_imports_reach_the_module_node_and_bind_the_name(graph):
    edges = _edges_from(graph, "app/main.py")
    assert ("imports", "code:module:app.pkg.mod") in edges
    assert ("imports", "code:function:app/pkg/mod.py::thing") in edges
    assert ("calls", "code:function:app/sibling.py::go") in edges
    assert not any(target.startswith("code:module:.") for _, target in edges)


def test_a_stdlib_import_never_binds_to_a_same_named_repo_module(graph):
    conn = sqlite3.connect(graph)
    try:
        row = conn.execute(
            "SELECT t.file_path FROM graph_edges_v12 e JOIN graph_nodes s ON s.id = e.source_id "
            "JOIN graph_nodes t ON t.id = e.target_id "
            "WHERE s.file_path = 'app/main.py' AND e.edge_type = 'imports' AND t.uid = 'code:module:types'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None and row[0] is None


def test_an_import_through_a_facade_reaches_the_function_that_defines_it(graph):
    edges = _edges_from(graph, "app/main.py")

    assert ("imports", "code:function:app/pkg/core.py::compute") in edges
    assert ("calls", "code:function:app/pkg/core.py::compute") in edges
