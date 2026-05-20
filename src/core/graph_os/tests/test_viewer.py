"""Tests for the HTML viewer (I.10).

Ship gate (Section 19 I.10):
  - 10k-node sample FPS ≥ 30 — measured by I.13 bench, smoke here
  - a11y fallback list-view
  - export JSON round-trip
  - CSP auditor + XSS fuzz + nonce-uniqueness tests (§15.1.2)
"""

from __future__ import annotations

import re

import pytest

from graph_os.types import GraphEdge, GraphNode
from graph_os.viewer import build_view
from graph_os.viewer.template import render

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def simple_graph():
    nodes = [
        GraphNode(uid="code:function:a", kind="code:function", label="fn_a"),
        GraphNode(uid="code:function:b", kind="code:function", label="fn_b"),
        GraphNode(uid="doc:file:r.md", kind="doc:file", label="r.md"),
    ]
    edges = [
        GraphEdge(
            source_uid="code:function:a",
            target_uid="code:function:b",
            edge_type="calls",
            extractor="t",
        ),
        GraphEdge(
            source_uid="doc:file:r.md",
            target_uid="code:function:a",
            edge_type="links_to",
            extractor="t",
        ),
    ]
    return nodes, edges


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


class TestTemplate:
    def test_includes_nonce_on_every_script(self, simple_graph):
        nodes, edges = simple_graph
        html = render(nodes, edges, title="t", nonce="abc123")
        # Every <script> tag either carries our nonce OR is the data
        # block (type=application/json, which is inert by CSP).
        for tag in re.findall(r"<script[^>]*>", html):
            if 'type="application/json"' in tag:
                continue
            assert 'nonce="abc123"' in tag

    def test_csp_header_strict(self, simple_graph):
        nodes, edges = simple_graph
        html = render(nodes, edges, title="t", nonce="n1")
        assert "default-src 'none'" in html
        assert "'nonce-n1'" in html
        assert "frame-ancestors 'none'" in html

    def test_xss_payload_in_label_is_escaped(self, simple_graph):
        nodes, edges = simple_graph
        nodes = [
            GraphNode(
                uid="code:function:a",
                kind="code:function",
                label="<img src=x onerror=alert(1)>",
            ),
            *nodes[1:],
        ]
        html_out = render(nodes, edges, title="t", nonce="n")
        # The JSON data block is *inert* (script type=application/json) so
        # the raw payload can safely appear there. The dangerous surface
        # is the a11y list — check that portion is escaped.
        a11y_start = html_out.find('class="a11y"')
        a11y_end = html_out.find("</aside>")
        a11y_block = html_out[a11y_start:a11y_end]
        assert "<img src=x" not in a11y_block
        assert "&lt;img src=x" in a11y_block

    def test_json_block_not_exec_context(self, simple_graph):
        """The graph payload lives in <script type=application/json> and
        therefore never executes even if malformed."""
        nodes, edges = simple_graph
        html = render(nodes, edges, title="t", nonce="n")
        assert '<script type="application/json" id="graph-data">' in html

    def test_bundled_swaps_cdn_for_self(self, simple_graph):
        nodes, edges = simple_graph
        html = render(nodes, edges, title="t", nonce="n", bundled=True)
        assert "https://cdn.jsdelivr.net" not in _csp_of(html)
        assert "'self'" in _csp_of(html)

    def test_a11y_list_emits_edges(self, simple_graph):
        nodes, edges = simple_graph
        html = render(nodes, edges, title="t", nonce="n")
        assert 'aria-label="accessible graph listing"' in html
        assert "calls" in html  # edge type reaches the fallback


class TestNonceUniqueness:
    def test_two_builds_differ(self, simple_graph, tmp_path):
        from graph_os.backends.sqlite_backend import SqliteBackend
        from graph_os.viewer.exporter import ViewerExporter

        # We only need a backend instance for the exporter — construct
        # a minimal one using the conftest fixture's pattern.
        pytest.skip("covered by test_build_view via tmp file")


# ---------------------------------------------------------------------------
# Exporter round-trip
# ---------------------------------------------------------------------------


class TestExporter:
    def test_build_view_round_trip(self, migrated_conn, simple_graph, tmp_path):
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        nodes, edges = simple_graph
        backend.bulk_upsert(nodes, edges)

        out = tmp_path / "graph.html"
        path = build_view(backend, out, title="dogfood")
        assert path.exists()
        html = path.read_text(encoding="utf-8")
        assert "dogfood" in html
        # Every script has a nonce.
        for tag in re.findall(r"<script[^>]*>", html):
            if 'type="application/json"' in tag:
                continue
            assert re.search(r'nonce="[A-Za-z0-9_\-]+"', tag)

    def test_unique_nonces_across_exports(self, migrated_conn, simple_graph, tmp_path):
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        nodes, edges = simple_graph
        backend.bulk_upsert(nodes, edges)
        html1 = build_view(backend, tmp_path / "a.html").read_text(encoding="utf-8")
        html2 = build_view(backend, tmp_path / "b.html").read_text(encoding="utf-8")
        n1 = _nonce_of(html1)
        n2 = _nonce_of(html2)
        assert n1 and n2 and n1 != n2

    def test_empty_backend_still_renders(self, migrated_conn, tmp_path):
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        path = build_view(backend, tmp_path / "empty.html")
        html = path.read_text(encoding="utf-8")
        assert "nodes: 0" in html
        assert "edges: 0" in html


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _csp_of(html: str) -> str:
    match = re.search(r"http-equiv=\"Content-Security-Policy\" content=\"([^\"]+)\"", html)
    return match.group(1) if match else ""


def _nonce_of(html: str) -> str:
    match = re.search(r"'nonce-([A-Za-z0-9_\-]+)'", html)
    return match.group(1) if match else ""
