"""How many files use a library: type-only imports, deep imports and sub-packages all count once per file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_typescript")

FILES = {
    "web/App.tsx": "import React, { useState } from 'react';\nexport const App = () => useState(1);\n",
    "web/types.ts": "import type { FC } from 'react';\nexport type Screen = FC;\n",
    "web/jsx.ts": "import { jsx } from 'react/jsx-runtime';\nexport const make = () => jsx('div', {});\n",
    "web/native.ts": "import { View } from 'react-native';\nexport const view = View;\n",
    "api/main.py": "import fastapi\n\napp = fastapi.FastAPI()\n",
    "api/test_main.py": "from fastapi.testclient import TestClient\n\nclient = TestClient\n",
    "go.mod": "module example.com/shop\n\ngo 1.22\n",
    "svc/server.go": (
        'package svc\n\nimport (\n\t"github.com/gofiber/fiber/v2"\n'
        '\t"github.com/gofiber/fiber/v2/middleware/cors"\n)\n\n'
        "func New() *fiber.App {\n\tapp := fiber.New()\n\tapp.Use(cors.New())\n\treturn app\n}\n"
    ),
    "svc/routes.go": (
        'package svc\n\nimport "github.com/gofiber/fiber/v2"\n\nfunc Mount(app *fiber.App) {}\n'
    ),
}


@pytest.fixture()
def references(tmp_path: Path, monkeypatch):
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

    def invoke(uid: str) -> dict:
        envelope = graph.cos_graph_references(uid)
        return json.loads(envelope)["data"] if isinstance(envelope, str) else envelope["data"]

    return invoke


def test_type_only_and_deep_imports_count_toward_the_package(references):
    react = references("code:module:npm:react")

    assert react["source_files"] == 3
    assert react["meta"]["merged_targets"] == ["code:module:npm:react/jsx-runtime"]


def test_a_python_submodule_import_counts_toward_its_package(references):
    assert references("code:module:fastapi")["source_files"] == 2


def test_a_go_subpackage_counts_toward_its_module_and_files_count_once(references):
    fiber = references("code:external:github.com/gofiber/fiber/v2")

    assert fiber["source_files"] == 2
    assert fiber["total_count"] == 3
