"""Tests for the frontend-fundamentals check_frontend.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "src" / "core" / "skills" / "frontend-fundamentals" / "scripts"))

import check_frontend as cf  # noqa: E402


def test_clean_component() -> None:
    code = "const style = useMemo(() => ({m:4}), []);\nreturn <Child style={style} key={it.id} />;"
    assert cf.scan_text(code, filename="ok.tsx") == []


def test_index_key_flagged() -> None:
    assert any("index as key" in f for f in cf.scan_text("<Row key={i} />", filename="x.tsx"))


def test_inline_object_prop_flagged() -> None:
    assert any("inline object" in f for f in cf.scan_text("<Child style={{margin: 4}} />", filename="x.tsx"))


def test_dangerous_html_flagged() -> None:
    assert any("dangerouslySetInnerHTML" in f
               for f in cf.scan_text("<div dangerouslySetInnerHTML={{__html: x}} />", filename="x.tsx"))


def test_comment_ignored() -> None:
    assert cf.scan_text("// <Child style={{m:4}} />", filename="x.tsx") == []
