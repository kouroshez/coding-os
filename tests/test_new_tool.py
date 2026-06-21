"""Tests for the mcp-tool-authoring new_tool.py scaffolder."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "src"
        / "templates"
        / "meta"
        / "skills"
        / "mcp-tool-authoring"
        / "scripts"
    ),
)

import new_tool as nt  # noqa: E402


def test_adds_cos_prefix() -> None:
    assert nt.normalize("my_thing") == "cos_my_thing"


def test_keeps_existing_prefix() -> None:
    assert nt.normalize("cos_already") == "cos_already"


def test_normalizes_separators() -> None:
    assert nt.normalize("My-Cool Tool") == "cos_my_cool_tool"


def test_render_has_envelope_and_layer() -> None:
    code = nt.render("widget", "graph")
    assert "@safe_tool" in code
    assert "@mcp.tool()" in code
    assert "def cos_widget(" in code
    assert 'fail("validation"' in code
    assert '"layer": "graph"' in code


def test_render_has_single_line_docstring() -> None:
    code = nt.render("widget", "memory")
    assert code.count('"""') == 2
