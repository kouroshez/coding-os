"""Tests for the graph-os-authoring new_extractor.py scaffolder."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "src" / "templates" / "meta" / "skills"
                       / "graph-os-authoring" / "scripts"))

import new_extractor as ne  # noqa: E402


def test_render_uses_lang_in_fn_name() -> None:
    assert "def extract_python(" in ne.render("python")


def test_render_sanitizes_lang() -> None:
    assert "def extract_go_fiber(" in ne.render("go-fiber")


def test_render_mentions_invariants() -> None:
    code = ne.render("python")
    assert "idempotent" in code
    assert "file_index_state" in code
    assert "Node" in code and "Edge" in code


def test_render_is_valid_python() -> None:
    import ast
    ast.parse(ne.render("typescript"))   # the scaffold must itself parse
