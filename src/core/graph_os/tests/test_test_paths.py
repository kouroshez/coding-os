"""One test-path rule: Go, TS and Jest layouts count as tests in every tool, not only Python ones."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from graph_os.test_paths import is_test_path


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("tests/test_api.py", True),
        ("app/test_models.py", True),
        ("app/conftest.py", True),
        ("internal/http/server_test.go", True),
        ("src/lib/price.test.ts", True),
        ("src/ui/Card.spec.tsx", True),
        ("src/hooks/__tests__/useCart.ts", True),
        ("internal/store/testdata/fixture.go", True),
        ("app/latest_values.py", False),
        ("src/contest/entry.ts", False),
        ("src/testing_utils.go", False),
        ("internal/http/server.go", False),
    ],
)
def test_is_test_path_knows_every_layout(path, expected):
    assert is_test_path(path) is expected


FILES = {
    "go.mod": "module example.com/shop\n\ngo 1.22\n",
    "src/lib/price.ts": "export function roundPrice(value: number): number {\n  return Math.round(value);\n}\n",
    "src/lib/price.test.ts": (
        "import { roundPrice } from './price';\ntest('rounds', () => {\n  roundPrice(1.2);\n});\n"
    ),
    "services/py/app.py": (
        "from fastapi import FastAPI\n\napp = FastAPI()\n\n\n"
        '@app.get("/health")\ndef health():\n    return {"ok": True}\n'
    ),
    "services/go/server.go": (
        'package server\n\nimport "github.com/gofiber/fiber/v2"\n\n'
        "func Register(app *fiber.App) {\n"
        '\tapp.Get("/health", health)\n}\n\n'
        'func health(c *fiber.Ctx) error {\n\treturn c.SendString("ok")\n}\n'
    ),
    "services/go/server_test.go": (
        'package server\n\nimport "github.com/gofiber/fiber/v2"\n\n'
        "func newTestApp() *fiber.App {\n\tapp := fiber.New()\n"
        '\tapp.Get("/health", health)\n\treturn app\n}\n'
    ),
}


@pytest.fixture()
def call(tmp_path: Path, monkeypatch):
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


def test_a_function_only_a_jest_test_calls_is_dead_but_tested(call):
    dead = {item["uid"] for item in call("cos_graph_dead_code")["data"]["dead"]}
    untested = {item["uid"] for item in call("cos_graph_test_gap")["data"]["untested"]}

    assert "code:function:src/lib/price.ts::roundPrice" in dead
    assert "code:function:src/lib/price.ts::roundPrice" not in untested


def test_contracts_list_each_service_that_serves_a_route_and_skip_test_apps(call):
    routes = call("cos_graph_contracts", kinds=["http"])["data"]["http_routes"]
    health = {(r["file_path"], r["framework"]) for r in routes if r["path"] == "/health"}

    assert health == {("services/py/app.py", "fastapi"), ("services/go/server.go", "fiber")}
