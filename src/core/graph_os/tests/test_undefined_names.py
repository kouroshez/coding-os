"""A name the code uses but never defines or imports is reported per file and line, in every language."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from graph_os.extractors._undefined_names import python_undefined, script_undefined
from graph_os.tree_sitter_overlay import parse

PYTHON = """from __future__ import annotations

import json

COUNTER = 0


def bump(path: Path) -> int:
    global COUNTER
    COUNTER += 1
    helper = json.dumps
    return len(helper(slugify(str(path))))


def configure():
    global SETTINGS
    SETTINGS = {}
"""

SCRIPT = """import { useMemo } from "react";
import type { Props } from "./types";

export function Card({ title, onPress }: Props) {
  const [open, setOpen] = useState(false);
  const label = useMemo(() => formatTitle(title), [title]);
  const timer = setTimeout(() => setOpen(true), 10);
  return (
    <View>
      <Header.Title text={label} />
      <div onClick={onPress} />
    </View>
  );
}

function formatTitle(value: string) {
  return new Intl.NumberFormat().format(Number(value)) + new Formatter().run();
}
"""


def _names(found: list[list]) -> set[str]:
    return {name for name, _ in found}


def test_python_reports_unbound_reads_and_annotation_only_names():
    found = python_undefined(PYTHON, ast.parse(PYTHON))

    assert _names(found) == {"Path", "slugify"}
    assert dict(map(tuple, found))["slugify"] == 12


def test_python_skips_a_file_with_a_star_import():
    source = "from os.path import *\n\nprint(join('a', 'b'))\n"
    assert python_undefined(source, ast.parse(source)) == []


def test_scripts_report_calls_constructors_and_components_never_bound():
    pytest.importorskip("tree_sitter_typescript")
    found = script_undefined(parse("tsx", SCRIPT).root)

    assert _names(found) == {"useState", "View", "Header", "Formatter"}


FILES = {
    "go.mod": "module example.com/shop\n\ngo 1.22\n",
    "app/tasks.py": "def run():\n    return schedule(1)\n",
    "web/Card.tsx": SCRIPT,
    "svc/util.go": "package svc\n\nfunc Format(v int) int { return v }\n",
    "svc/use.go": ("package svc\n\nfunc Use() int {\n\treturn Format(1) + Missing(2)\n}\n"),
}


@pytest.fixture()
def call(tmp_path: Path, monkeypatch):
    pytest.importorskip("tree_sitter_go")
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools import graph
    from graph_os.tools.reindex_dispatch import dispatch

    (tmp_path / ".coding-os").mkdir()
    for relative, text in FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    db = str(tmp_path / "graph.db")
    for relative in FILES:
        dispatch(tmp_path / relative, project_root=tmp_path, db_path=db, include_docs=False)
    test_backend = SqliteBackend(conn=init_db(db))
    test_backend.link_cross_file()
    monkeypatch.setattr(graph, "_backend", lambda *, backend=None: test_backend)

    def invoke(name: str, **kwargs):
        envelope = getattr(graph, name)(**kwargs)
        return json.loads(envelope) if isinstance(envelope, str) else envelope

    return invoke


def test_the_tool_lists_every_language_and_detect_changes_names_the_edited_file(call):
    listed = {
        (item["file"], item["name"], item["lang"])
        for item in call("cos_graph_undefined")["data"]["undefined"]
    }
    changed = call("cos_graph_detect_changes", files=["svc/use.go"])["data"]["undefined_names"]

    assert {
        ("app/tasks.py", "schedule", "py"),
        ("web/Card.tsx", "useState", "tsx"),
        ("svc/use.go", "Missing", "go"),
    } <= listed
    assert not any(
        item["name"] == "Format" for item in call("cos_graph_undefined")["data"]["undefined"]
    )
    assert [(item["name"], item["line"]) for item in changed] == [("Missing", 4)]


def test_a_python_import_of_a_name_its_module_does_not_define_is_reported(tmp_path, monkeypatch):
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools import graph
    from graph_os.tools.reindex_dispatch import dispatch

    files = {
        "app/__init__.py": "",
        "app/deps.py": "from .base import shared\n\n\ndef get_db():\n    return 1\n",
        "app/base.py": "def shared():\n    return 1\n",
        "app/dynamic.py": "def __getattr__(name):\n    return name\n",
        "app/starred.py": "from .base import *\n",
        "app/api.py": (
            "from app.deps import get_db, removed_fn, shared\n"
            "from app import deps\n"
            "from app.dynamic import anything\n"
            "from app.starred import whatever\n"
            "from requests import get\n"
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
    test_backend = SqliteBackend(conn=init_db(db))
    test_backend.link_cross_file()
    monkeypatch.setattr(graph, "_backend", lambda *, backend=None: test_backend)

    envelope = graph.cos_graph_undefined()
    found = json.loads(envelope)["data"]["undefined"] if isinstance(envelope, str) else envelope
    broken = {(item["name"], item["reason"]) for item in found if item["file"] == "app/api.py"}

    assert broken == {("removed_fn", "not_exported")}


def test_a_go_call_into_a_package_never_imported_is_reported(tmp_path, monkeypatch):
    pytest.importorskip("tree_sitter_go")
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools import graph
    from graph_os.tools.reindex_dispatch import dispatch

    files = {
        "go.mod": "module example.com/shop\n\ngo 1.22\n",
        "svc/db.go": 'package svc\n\nimport "database/sql"\n\nvar db *sql.DB\n',
        "svc/use.go": (
            "package svc\n\n"
            'import "fmt"\n\n'
            "func Use(name string) error {\n"
            "\tfmt.Println(name)\n"
            "\tdb.Ping()\n"
            "\treturn errors.New(strings.ToUpper(name))\n"
            "}\n"
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
    test_backend = SqliteBackend(conn=init_db(db))
    test_backend.link_cross_file()
    monkeypatch.setattr(graph, "_backend", lambda *, backend=None: test_backend)

    envelope = graph.cos_graph_undefined()
    found = json.loads(envelope)["data"]["undefined"] if isinstance(envelope, str) else envelope
    missing = {
        (item["name"], item["line"], item["reason"])
        for item in found
        if item["file"] == "svc/use.go"
    }

    assert missing == {("errors", 8, "not_imported"), ("strings", 8, "not_imported")}


def test_ts_checks_names_through_barrels_and_trusts_commonjs_and_ambient_declarations(
    tmp_path, monkeypatch
):
    pytest.importorskip("tree_sitter_typescript")
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools import graph
    from graph_os.tools.reindex_dispatch import dispatch

    files = {
        "package.json": '{"name": "web"}',
        "ui/Button.ts": "export const Button = 1;\n",
        "ui/index.ts": "export * from './Button';\n",
        "lib/single.js": "exports.bar = () => 2;\n",
        "types/env.d.ts": "declare function track(name: string): void;\n",
        "app/use.ts": (
            "import { Button, Missing } from '../ui';\n"
            "import { bar } from '../lib/single';\n"
            "export const x = [Button, Missing, bar];\n"
            "track('x');\n"
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
    test_backend = SqliteBackend(conn=init_db(db))
    test_backend.link_cross_file()
    monkeypatch.setattr(graph, "_backend", lambda *, backend=None: test_backend)

    envelope = graph.cos_graph_undefined()
    found = json.loads(envelope)["data"]["undefined"] if isinstance(envelope, str) else envelope
    reported = {(item["name"], item["reason"]) for item in found if item["file"] == "app/use.ts"}

    assert reported == {("Missing", "not_exported")}
