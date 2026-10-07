"""A caller keeps its edge when the symbol it calls is removed and comes back, or moves to a new file."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_go")
pytest.importorskip("tree_sitter_typescript")


def _save(root: Path, db: str, relative: str, text: str | None) -> None:
    from graph_os.tools.reindex_dispatch import dispatch

    path = root / relative
    if text is None:
        path.unlink()
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    dispatch(path, project_root=root, db_path=db, include_docs=False)


def _targets(db: str, caller: str, edge_type: str) -> set[str]:
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT t.uid FROM graph_edges_v12 e JOIN graph_nodes s ON s.id = e.source_id "
            "JOIN graph_nodes t ON t.id = e.target_id WHERE s.uid = ? AND e.edge_type = ?",
            (caller, edge_type),
        ).fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


@pytest.fixture()
def repo(tmp_path: Path) -> tuple[Path, str]:
    (tmp_path / ".coding-os").mkdir()
    (tmp_path / "go.mod").write_text("module example.com/shop\n\ngo 1.22\n", encoding="utf-8")
    return tmp_path, str(tmp_path / "graph.db")


CASES = {
    "python": (
        ("app/__init__.py", ""),
        ("app/use.py", "from .lib import helper\n\n\ndef run():\n    return helper()\n"),
        ("app/lib.py", "def helper():\n    return 1\n"),
        "code:function:app/use.py::run",
        "calls",
        "code:function:app/lib.py::helper",
        ("app/lib.py", "def other():\n    return 2\n"),
    ),
    "typescript": (
        (
            "web/use.ts",
            "import { helper } from './lib';\nexport function run() {\n  return helper();\n}\n",
        ),
        ("web/lib.ts", "export function helper() {\n  return 1;\n}\n"),
        None,
        "code:function:web/use.ts::run",
        "calls",
        "code:function:web/lib.ts::helper",
        ("web/lib.ts", "export function other() {\n  return 2;\n}\n"),
    ),
    "go": (
        ("svc/use.go", "package svc\n\nfunc Run() int {\n\treturn Helper()\n}\n"),
        ("svc/lib.go", "package svc\n\nfunc Helper() int {\n\treturn 1\n}\n"),
        None,
        "code:function:svc/use.go::Run",
        "calls",
        "code:function:svc/lib.go::Helper",
        ("svc/lib.go", "package svc\n\nfunc Other() int {\n\treturn 2\n}\n"),
    ),
    "shell": (
        (
            "bin/use.sh",
            '#!/usr/bin/env bash\nsource "$(dirname "$0")/lib.sh"\nrun() {\n  helper\n}\n',
        ),
        ("bin/lib.sh", "#!/usr/bin/env bash\nhelper() {\n  echo 1\n}\n"),
        None,
        "code:function:bin/use.sh::run",
        "calls",
        "code:function:bin/lib.sh::helper",
        ("bin/lib.sh", "#!/usr/bin/env bash\nother() {\n  echo 2\n}\n"),
    ),
}


@pytest.mark.parametrize("language", sorted(CASES))
def test_a_symbol_removed_and_restored_gets_its_callers_back(repo, language):
    root, db = repo
    first, second, third, caller, edge_type, callee, without = CASES[language]
    for relative, text in [item for item in (first, second, third) if item]:
        _save(root, db, relative, text)
    assert callee in _targets(db, caller, edge_type)

    _save(root, db, *without)
    assert callee not in _targets(db, caller, edge_type)
    _save(root, db, *(second if third is None else third))

    assert callee in _targets(db, caller, edge_type)


def test_a_go_function_moved_to_a_new_file_keeps_its_callers(repo):
    root, db = repo
    _save(root, db, "svc/use.go", "package svc\n\nfunc Run() int {\n\treturn Helper()\n}\n")
    _save(root, db, "svc/lib.go", "package svc\n\nfunc Helper() int {\n\treturn 1\n}\n")
    _save(root, db, "svc/lib.go", None)
    _save(root, db, "svc/moved.go", "package svc\n\nfunc Helper() int {\n\treturn 1\n}\n")

    assert "code:function:svc/moved.go::Helper" in _targets(
        db, "code:function:svc/use.go::Run", "calls"
    )
