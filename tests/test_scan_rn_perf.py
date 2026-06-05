"""Tests for the react-native-patterns scan_rn_perf.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "src" / "templates" / "react-native" / "skills"
                       / "react-native-patterns" / "scripts"))

import scan_rn_perf as rn  # noqa: E402


def test_clean_list() -> None:
    code = "<FlatList data={d} keyExtractor={kx} renderItem={renderRow} />"
    assert rn.scan_text(code, filename="ok.tsx") == []


def test_inline_render_item_flagged() -> None:
    out = rn.scan_text("<FlatList renderItem={({item}) => <Row item={item} />} keyExtractor={kx} />",
                       filename="x.tsx")
    assert any("inline renderItem" in f for f in out)


def test_missing_key_extractor_flagged() -> None:
    out = rn.scan_text("<FlatList data={d} renderItem={renderRow} />", filename="x.tsx")
    assert any("keyExtractor" in f for f in out)


def test_inline_style_flagged() -> None:
    out = rn.scan_text("<View style={{ padding: 16 }} />", filename="x.tsx")
    assert any("inline style" in f for f in out)


def test_comment_ignored() -> None:
    assert rn.scan_text("// <View style={{padding:1}} />", filename="x.tsx") == []
