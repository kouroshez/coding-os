"""Python: module-level calls, `TYPE_CHECKING`-only importers, the undefined-name scopes, the tree-sitter path."""

from __future__ import annotations

import sqlite3
import textwrap
from pathlib import Path

import pytest


def _extract(path: str, source: str):
    from graph_os.extractors import code_python

    return code_python.extract(path, textwrap.dedent(source))


def test_a_call_inside_a_def_under_a_module_level_if_belongs_to_the_def_only():
    result = _extract(
        "app/compat.py",
        """
        import sys

        def helper():
            return 1

        if sys.version_info >= (3, 11):
            def modern():
                return helper()
        else:
            setup = helper()

        try:
            import fast
        except ImportError:
            class Fallback:
                def run(self):
                    return helper()
        """,
    )
    callers = {
        edge.source_uid
        for edge in result.edges
        if edge.edge_type == "calls" and edge.target_uid.endswith("::helper")
    }

    assert callers == {
        "code:function:app/compat.py::modern",
        "code:module:app.compat",
        "code:method:app/compat.py::Fallback.run",
    }
    module_calls = [
        edge
        for edge in result.edges
        if edge.edge_type == "calls"
        and edge.source_uid == "code:module:app.compat"
        and edge.target_uid.endswith("::helper")
    ]
    assert [edge.source_span for edge in module_calls] == ["app/compat.py:11"]


def test_an_importer_whose_only_import_is_type_checking_links_to_the_module(tmp_path: Path):
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools.reindex_dispatch import dispatch

    files = {
        "pyproject.toml": "[project]\nname = 'shop'\n",
        "shop/__init__.py": "",
        "shop/models.py": "class User:\n    pass\n",
        "shop/service.py": (
            "from __future__ import annotations\n\nfrom typing import TYPE_CHECKING\n\n"
            "if TYPE_CHECKING:\n    from shop.models import User\n\n\n"
            "def greet(user: User) -> str:\n    return 'hi'\n"
        ),
    }
    (tmp_path / ".coding-os").mkdir()
    for relative, text in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    db = str(tmp_path / "graph.db")
    for relative in files:
        dispatch(tmp_path / relative, project_root=tmp_path, db_path=db, include_docs=False)
    SqliteBackend(conn=init_db(db)).link_cross_file()
    conn = sqlite3.connect(db)
    try:
        targets = {
            (str(kind), str(path))
            for kind, path in conn.execute(
                "SELECT e.edge_type, t.file_path FROM graph_edges_v12 e "
                "JOIN graph_nodes s ON s.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id "
                "WHERE s.uid = 'code:module:shop.service' AND e.edge_type LIKE 'imports%'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert ("imports_type", "shop/models.py") in targets


def _undefined(source: str) -> set[str]:
    import ast

    from graph_os.extractors._undefined_python import python_undefined

    text = textwrap.dedent(source)
    return {name for name, _ in python_undefined(text, ast.parse(text))}


def test_a_comprehension_walrus_and_class_dunders_are_bound():
    assert not _undefined(
        """
        data = [1, 2]
        squares = [last := value * value for value in data]
        print(last)

        class Model:
            label = __qualname__
            home = __module__
        """
    )


def test_a_name_only_a_string_annotation_or_a_shadowed_annotation_uses_is_reported():
    assert _undefined(
        """
        from __future__ import annotations

        def load(path: "Missing") -> "list[Other]":
            return []

        def greet(name: "username") -> "greeting":
            return name

        def unrelated():
            Ghost = 1
            return Ghost

        def build(value: Ghost) -> None:
            return None
        """
    ) == {"Missing", "Other", "Ghost"}


def test_annotations_resolve_against_enclosing_scopes():
    assert not _undefined(
        """
        from __future__ import annotations

        def outer():
            from decimal import Decimal

            def inner(amount: Decimal) -> Decimal:
                return amount

            return inner

        class Node:
            Child = int

            def first(self, child: Child) -> Node:
                return self
        """
    )


def test_the_tree_sitter_import_path_keeps_type_checking_and_fallback_bindings(monkeypatch):
    pytest.importorskip("tree_sitter_python")
    source = """
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            from shop.models import User

        try:
            import ujson as json
        except ImportError:
            import json

        def dump(user: User) -> str:
            return json.dumps(user)
        """
    monkeypatch.setenv("COS_EXTRACTOR_PREFERENCE", "legacy")
    legacy = _extract("app/dump.py", source)
    monkeypatch.setenv("COS_EXTRACTOR_PREFERENCE", "tree-sitter")
    tree_sitter = _extract("app/dump.py", source)

    def shape(result) -> set[tuple[str, str, str]]:
        return {
            (edge.source_uid, edge.target_uid, edge.edge_type)
            for edge in result.edges
            if edge.edge_type in ("imports", "imports_type", "calls")
        }

    assert shape(tree_sitter) == shape(legacy)
