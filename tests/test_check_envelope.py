"""Tests for the python-meta-server check_envelope.py (Rule 13 linter)."""

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
        / "python-meta-server"
        / "scripts"
    ),
)

import check_envelope as ce  # noqa: E402

GOOD = '''
@safe_tool
@mcp.tool()
def cos_widget(arg: str) -> dict:
    """Do a thing."""
    return ok({"x": 1})
'''


def test_compliant_tool_clean() -> None:
    assert ce.scan_source(GOOD, filename="ok.py") == []


def test_missing_safe_tool_flagged() -> None:
    src = "@mcp.tool()\ndef cos_widget(a):\n    return ok({})\n"
    assert any("not @safe_tool" in f for f in ce.scan_source(src, filename="x.py"))


def test_missing_cos_prefix_flagged() -> None:
    src = "@safe_tool\n@mcp.tool()\ndef widget(a):\n    return ok({})\n"
    assert any("cos_ prefix" in f for f in ce.scan_source(src, filename="x.py"))


def test_no_envelope_return_flagged() -> None:
    src = '@safe_tool\n@mcp.tool()\ndef cos_widget(a):\n    return {"x": 1}\n'
    assert any("never returns ok()/fail()" in f for f in ce.scan_source(src, filename="x.py"))


def test_non_tool_function_ignored() -> None:
    assert ce.scan_source("def helper(x):\n    return x\n", filename="x.py") == []
