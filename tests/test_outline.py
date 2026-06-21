"""Tests for the codebase-explorer outline.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "src"
        / "core"
        / "skills"
        / "codebase-explorer"
        / "scripts"
    ),
)

import outline as ol  # noqa: E402

PY = """
class Foo:
    def method_a(self):
        pass

def top_level():
    pass
"""


def test_python_classes_and_functions() -> None:
    items = ol.outline_python(PY)
    names = {(i["kind"], i["name"]) for i in items}
    assert ("class", "Foo") in names
    assert ("func", "method_a") in names
    assert ("func", "top_level") in names


def test_python_nesting_depth() -> None:
    items = ol.outline_python(PY)
    method = next(i for i in items if i["name"] == "method_a")
    top = next(i for i in items if i["name"] == "top_level")
    assert method["depth"] == 1 and top["depth"] == 0


def test_ts_top_level_decls() -> None:
    ts = (
        "export class Service {}\nexport const config = 1;\ninterface User {}\nfunction helper() {}"
    )
    items = ol.outline_ts(ts)
    kinds = {(i["kind"], i["name"]) for i in items}
    assert ("class", "Service") in kinds
    assert ("const", "config") in kinds
    assert ("interface", "User") in kinds
    assert ("function", "helper") in kinds
