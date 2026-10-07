"""`self.m()`, `cls.m()` and `super().m()` reach the base class method; `cls()` constructs the class."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

FILES = {
    "app/__init__.py": "",
    "app/base.py": (
        "class Base:\n"
        "    def save(self):\n        return 1\n\n"
        "    @classmethod\n    def load(cls):\n        return cls()\n"
    ),
    "app/child.py": (
        "from .base import Base\n\n\n"
        "class Child(Base):\n"
        "    def save(self):\n        return super().save()\n\n"
        "    def run(self):\n        return self.save()\n\n"
        "    @classmethod\n    def fresh(cls):\n        return cls.load()\n"
    ),
    "app/grand.py": (
        "from .child import Child\n\n\n"
        "class GrandChild(Child):\n"
        "    def go(self):\n        return self.load(), self.missing()\n"
    ),
}


@pytest.fixture()
def edges(tmp_path: Path) -> set[tuple[str, str, str]]:
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
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT s.uid, e.edge_type, t.uid FROM graph_edges_v12 e "
            "JOIN graph_nodes s ON s.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id "
            "WHERE e.edge_type IN ('calls', 'constructs')"
        ).fetchall()
    finally:
        conn.close()
    return {(_name(s), kind, _name(t)) for s, kind, t in rows}


def _name(uid: str) -> str:
    return uid.rpartition("::")[2] if "::" in uid else uid.rpartition(":")[2]


def test_super_reaches_the_base_method_in_another_file(edges):
    assert ("Child.save", "calls", "Base.save") in edges


def test_self_reaches_an_own_override_before_the_base(edges):
    assert ("Child.run", "calls", "Child.save") in edges
    assert ("Child.run", "calls", "Base.save") not in edges


def test_self_and_cls_reach_a_method_two_bases_up(edges):
    assert ("Child.fresh", "calls", "Base.load") in edges
    assert ("GrandChild.go", "calls", "Base.load") in edges


def test_cls_call_constructs_the_class(edges):
    assert ("Base.load", "constructs", "Base") in edges


def test_a_method_no_base_defines_stays_unresolved(edges):
    assert ("GrandChild.go", "calls", "self.missing") in edges


def _build(root: Path, files: dict[str, str], db: str) -> None:
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools.reindex_dispatch import dispatch

    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        dispatch(path, project_root=root, db_path=db, include_docs=False)
        SqliteBackend(conn=init_db(db)).link_cross_file(file_path=relative)


def _call_targets(db: str, caller: str) -> set[str]:
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT t.uid FROM graph_edges_v12 e JOIN graph_nodes s ON s.id = e.source_id "
            "JOIN graph_nodes t ON t.id = e.target_id "
            "WHERE e.edge_type = 'calls' AND s.uid LIKE ?",
            (f"%::{caller}",),
        ).fetchall()
    finally:
        conn.close()
    return {_name(row[0]) for row in rows}


def test_an_edit_to_a_base_moves_the_inherited_call_it_affects(tmp_path: Path):
    (tmp_path / ".coding-os").mkdir()
    db = str(tmp_path / "graph.db")
    _build(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/base.py": "class Base:\n    def helper(self):\n        return 1\n",
            "app/mid.py": "from .base import Base\n\n\nclass Mid(Base):\n    pass\n",
            "app/derived.py": (
                "from .mid import Mid\n\n\nclass Derived(Mid):\n"
                "    def run(self):\n        return self.helper()\n"
            ),
        },
        db,
    )
    assert "Base.helper" in _call_targets(db, "Derived.run")

    _build(
        tmp_path,
        {
            "app/mid.py": (
                "from .base import Base\n\n\nclass Mid(Base):\n"
                "    def helper(self):\n        return 2\n"
            )
        },
        db,
    )
    assert "Mid.helper" in _call_targets(db, "Derived.run")
    assert "Base.helper" not in _call_targets(db, "Derived.run")


def test_the_base_walk_follows_the_c3_method_resolution_order(tmp_path: Path):
    (tmp_path / ".coding-os").mkdir()
    db = str(tmp_path / "graph.db")
    _build(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/views.py": (
                "class AuthMixin:\n    def check(self):\n        return 'auth'\n\n\n"
                "class PermissionMixin(AuthMixin):\n    pass\n\n\n"
                "class BaseView:\n    def check(self):\n        return 'base'\n"
            ),
            "app/my.py": (
                "from .views import BaseView, PermissionMixin\n\n\n"
                "class MyView(PermissionMixin, BaseView):\n"
                "    def go(self):\n        return self.check()\n"
            ),
        },
        db,
    )

    assert "AuthMixin.check" in _call_targets(db, "MyView.go")
    assert "BaseView.check" not in _call_targets(db, "MyView.go")


def test_the_c3_merge_matches_the_python_org_reference_example():
    # ex_9 of "The Python 2.3 Method Resolution Order": L[Z] = Z K1 K2 K3 D A B C E O.
    from graph_os.backends._sqlite_links_py_inherited import _c3_merge

    k1, k2, k3 = ["K1", "A", "B", "C", "O"], ["K2", "D", "B", "E", "O"], ["K3", "D", "A", "O"]

    assert _c3_merge([k1, k2, k3, ["K1", "K2", "K3"]]) == [
        "K1",
        "K2",
        "K3",
        "D",
        "A",
        "B",
        "C",
        "E",
        "O",
    ]
