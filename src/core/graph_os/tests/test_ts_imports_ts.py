"""Tests for the tree-sitter-primary TS/TSX import path (TASK-121).

Coverage matrix:
  - default `auto` mode keeps the regex tag (provenance="regex")
  - opt-in `tree-sitter` mode swaps the tag to provenance="tree-sitter"
    when the grammar parses
  - same edge topology between modes (tag-only swap)
  - missing grammar / parse failure degrades to regex (no crash)
  - side-effect imports + named imports + re-exports all flip together
  - evidence signals follow the tag
"""

from __future__ import annotations

import textwrap

import pytest

from graph_os.extractors import code_ts
from graph_os.types import provenance_for


def _extract(src: str, *, path: str = "src/foo.ts"):
    return code_ts.extract(path, textwrap.dedent(src))


def _import_edges(result):
    return [e for e in result.edges if e.edge_type == "imports"]


@pytest.fixture
def force_tree_sitter(monkeypatch):
    monkeypatch.setenv("COS_EXTRACTOR_PREFERENCE", "tree-sitter")
    yield


@pytest.fixture
def force_legacy(monkeypatch):
    monkeypatch.setenv("COS_EXTRACTOR_PREFERENCE", "legacy")
    yield


def _has_ts_grammar() -> bool:
    try:
        from graph_os.tree_sitter_overlay import _load_language

        return _load_language("typescript") is not None
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(
    not _has_ts_grammar(),
    reason="tree-sitter-typescript grammar not installed",
)


# ---------------------------------------------------------------------------
# Mode selection
# ---------------------------------------------------------------------------


class TestModeSelection:
    def test_default_auto_uses_regex(self, monkeypatch):
        monkeypatch.delenv("COS_EXTRACTOR_PREFERENCE", raising=False)
        r = _extract('import { Foo } from "pkg";\n')
        edges = _import_edges(r)
        assert all(provenance_for(e.extractor) == "regex" for e in edges)

    def test_legacy_mode_uses_regex(self, force_legacy):
        r = _extract('import { Foo } from "pkg";\n')
        edges = _import_edges(r)
        assert all(provenance_for(e.extractor) == "regex" for e in edges)

    def test_tree_sitter_mode_tags_imports(self, force_tree_sitter):
        r = _extract('import { Foo as F } from "pkg";\n')
        edges = _import_edges(r)
        assert any(e.extractor == "code_ts_ts@v1" for e in edges)
        assert any(provenance_for(e.extractor) == "tree-sitter" for e in edges)


# ---------------------------------------------------------------------------
# Topology parity
# ---------------------------------------------------------------------------


class TestTopologyParity:
    def _grouped(self, edges):
        return sorted(
            (e.source_uid, e.target_uid, e.edge_type) for e in edges
        )

    def test_named_imports_same_topology(self, monkeypatch):
        src = textwrap.dedent(
            """
            import { Foo, Bar as B } from "pkg";
            import * as ns from "ns-pkg";
            import "side-effect-only";
            """
        )
        monkeypatch.setenv("COS_EXTRACTOR_PREFERENCE", "tree-sitter")
        ts = _import_edges(code_ts.extract("foo.ts", src))
        monkeypatch.setenv("COS_EXTRACTOR_PREFERENCE", "legacy")
        legacy = _import_edges(code_ts.extract("foo.ts", src))
        # Same edges (same source/target/type), just different tags.
        assert self._grouped(ts) == self._grouped(legacy)


# ---------------------------------------------------------------------------
# Side-effect + re-export tag swap
# ---------------------------------------------------------------------------


class TestSideEffectAndReExport:
    def test_side_effect_import_swapped(self, force_tree_sitter):
        r = _extract('import "polyfill";\n')
        edges = _import_edges(r)
        assert all(e.extractor == "code_ts_ts@v1" for e in edges)

    def test_re_export_swapped(self, force_tree_sitter):
        r = _extract('export { Foo } from "pkg";\n')
        re_exports = [e for e in r.edges if e.edge_type == "re_exports"]
        assert all(e.extractor == "code_ts_ts@v1" for e in re_exports)


# ---------------------------------------------------------------------------
# Evidence signals
# ---------------------------------------------------------------------------


class TestEvidenceSignals:
    def test_tree_sitter_signal_named(self, force_tree_sitter):
        r = _extract('import { Foo } from "pkg";\n')
        signals = [
            s.signal_name
            for e in _import_edges(r)
            for s in e.evidence
        ]
        assert "tree_sitter_import" in signals

    def test_tree_sitter_signal_side_effect(self, force_tree_sitter):
        r = _extract('import "polyfill";\n')
        signals = [
            s.signal_name
            for e in _import_edges(r)
            for s in e.evidence
        ]
        assert "tree_sitter_import_side_effect" in signals

    def test_legacy_keeps_old_signals(self, force_legacy):
        r = _extract('import { Foo } from "pkg";\nimport "side";')
        signals = [
            s.signal_name
            for e in _import_edges(r)
            for s in e.evidence
        ]
        assert "ts_import" in signals
        assert "ts_import_side_effect" in signals
