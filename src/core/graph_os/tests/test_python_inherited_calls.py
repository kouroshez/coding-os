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
