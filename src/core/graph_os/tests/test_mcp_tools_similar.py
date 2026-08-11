"""cos_graph_* MCP tools — similarity ranking and cluster usability.

The seeded fixture graph comes from the directory conftest.
"""

from __future__ import annotations

import json

import pytest

from graph_os.tools import graph
from graph_os.types import GraphEdge, GraphNode

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _decode(envelope):
    if isinstance(envelope, str):
        return json.loads(envelope)
    return envelope


def _assert_ok(envelope) -> dict:
    env = _decode(envelope)
    assert env["ok"] is True, f"expected ok envelope, got {env}"
    data = env["data"]
    assert data["meta"]["layer"] == "graph"
    return data


def _assert_fail(envelope, category: str) -> None:
    env = _decode(envelope)
    assert env["ok"] is False
    assert env["error"]["category"] == category


class TestClusterThreeUsability:
    """Graph-tool usability fixes: dead_code FP, impact visit_limit + freshness."""

    def test_dead_code_skips_exception_classes(self, seeded_backend):
        seeded_backend.bulk_upsert(
            [
                GraphNode(
                    uid="code:class:err.py::WidgetError",
                    kind="code:class",
                    label="WidgetError",
                    file_path="err.py",
                )
            ],
            [],
        )
        data = _assert_ok(graph.cos_graph_dead_code(kind="class"))
        labels = {d["label"] for d in data["dead"]}
        assert "WidgetError" not in labels, "exception classes must not be flagged dead (FP)"

    def test_impact_accepts_visit_limit(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_impact("code:function:a.py::foo", visit_limit=10))
        assert data["meta"]["visit_limit"] == 10

    def test_impact_surfaces_freshness(self, seeded_backend, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "t.py").write_text("value = 1\n", encoding="utf-8")
        seeded_backend.bulk_upsert(
            [
                GraphNode(
                    uid="code:file:t.py",
                    kind="code:file",
                    label="t.py",
                    file_path="t.py",
                    content_hash="0000000000000000",
                ),
                GraphNode(
                    uid="code:function:t.py::g",
                    kind="code:function",
                    label="g",
                    file_path="t.py",
                ),
            ],
            [],
        )
        data = _assert_ok(graph.cos_graph_impact("code:function:t.py::g"))
        assert data["meta"]["stale"] is True


class TestSimilar:
    def test_happy_path(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_similar("code:function:a.py::foo", confidence_min=0.0, top_k=5)
        )
        assert "results" in data

    def test_unknown_uid(self, seeded_backend):
        _assert_fail(graph.cos_graph_similar("code:function:missing"), "not_found")

    def test_top_k_honoured(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_similar("code:function:a.py::foo", top_k=2, confidence_min=0.0)
        )
        assert len(data["results"]) <= 2

    def test_confidence_floor_excludes_low(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_similar("code:function:a.py::foo", confidence_min=0.99, top_k=5)
        )
        assert all(r["similarity"] >= 0.99 for r in data["results"])

    def test_sibling_augmentation_surfaces_container_twin(self, migrated_conn, monkeypatch):
        """Round-5 audit: sample_nodes draws a fixed id-prefix window, so a
        structural twin outside that window was never even a candidate
        (count_nodes' twin count_edges, same class). The CONTAINS sibling
        sweep must guarantee same-container nodes are scored even when the
        sample omits them entirely."""
        from graph_os.backends.sqlite_backend import SqliteBackend

        be = SqliteBackend(conn=migrated_conn)
        be.bulk_upsert(
            [
                GraphNode(
                    uid="code:class:m.py::C",
                    kind="code:class",
                    label="C",
                    file_path="m.py",
                    start_line=1,
                ),
                GraphNode(
                    uid="code:method:m.py::C.alpha",
                    kind="code:method",
                    label="alpha",
                    file_path="m.py",
                    start_line=2,
                ),
                GraphNode(
                    uid="code:method:m.py::C.beta",
                    kind="code:method",
                    label="beta",
                    file_path="m.py",
                    start_line=8,
                ),
            ],
            [
                GraphEdge(
                    source_uid="code:class:m.py::C",
                    target_uid="code:method:m.py::C.alpha",
                    edge_type="contains",
                    extractor="test",
                    confidence=1.0,
                ),
                GraphEdge(
                    source_uid="code:class:m.py::C",
                    target_uid="code:method:m.py::C.beta",
                    edge_type="contains",
                    extractor="test",
                    confidence=1.0,
                ),
            ],
        )
        # Force the sample window to EXCLUDE everything — now ONLY the
        # CONTAINS sibling sweep can surface the twin.
        monkeypatch.setattr(be, "sample_nodes", lambda kind, limit: [])
        graph._BACKEND_SINGLETON = be
        monkeypatch.setattr(graph, "_backend", lambda *, backend=None: be)
        data = _assert_ok(
            graph.cos_graph_similar("code:method:m.py::C.alpha", confidence_min=0.0, top_k=5)
        )
        graph._BACKEND_SINGLETON = None
        uids = [r["uid"] for r in data["results"]]
        assert "code:method:m.py::C.beta" in uids

    def test_graph_search_hybrid_returns_relevant(self, migrated_conn, monkeypatch):
        """Wave 3: cos_graph_search ranks code symbols by free text via the
        hybrid semantic + lexical + centrality blend."""
        pytest.importorskip("sentence_transformers")
        import embeddings as emb  # type: ignore

        from graph_os.backends.sqlite_backend import SqliteBackend

        # is_available() only proves the package imports; offline CI has no
        # model weights, so probe the actual load like thinking_os/conftest.
        if emb._get_model() is None:
            pytest.skip("real embedding model unavailable (offline / not vendored)")

        be = SqliteBackend(conn=migrated_conn)
        nodes = [
            GraphNode(
                uid="code:function:a.py::validate_jwt",
                kind="function",
                label="validate_jwt",
                file_path="a.py",
                start_line=1,
                signature="def validate_jwt(token)",
                doc_blob="Verify a JWT auth token signature and expiry.",
            ),
            GraphNode(
                uid="code:function:a.py::render_chart",
                kind="function",
                label="render_chart",
                file_path="a.py",
                start_line=9,
                signature="def render_chart(rows)",
                doc_blob="Draw a bar chart from rows.",
            ),
        ]
        be.bulk_upsert(nodes, [])
        for n in nodes:
            row = migrated_conn.execute(
                "SELECT id, signature, doc_blob FROM graph_nodes WHERE uid = ?", (n.uid,)
            ).fetchone()
            emb.upsert_embedding(
                migrated_conn,
                "graph_nodes",
                row[0],
                " ".join(filter(None, [n.label, row[1], row[2]])),
            )
        migrated_conn.commit()

        graph._BACKEND_SINGLETON = be
        monkeypatch.setattr(graph, "_backend", lambda *, backend=None: be)
        try:
            res = graph.cos_graph_search("verify authentication token", top_k=5)
        finally:
            graph._BACKEND_SINGLETON = None

        data = _assert_ok(res)
        assert data["meta"]["scorer"] == "hybrid"
        uids = [r["uid"] for r in data["results"]]
        assert "code:function:a.py::validate_jwt" in uids
        assert uids[0] == "code:function:a.py::validate_jwt"

    def test_graph_search_rejects_empty_query(self, seeded_backend):
        _assert_fail(graph.cos_graph_search(""), "validation")

    def test_persisted_embeddings_fast_path(self, migrated_conn, monkeypatch):
        """Wave 1: when graph_nodes carry persisted embeddings, cos_graph_similar
        ranks from stored vectors (scorer='persisted-embeddings') — one query
        encode over the full pool, no per-candidate on-the-fly encoding."""
        pytest.importorskip("sentence_transformers")
        import embeddings as emb  # type: ignore

        from graph_os.backends.sqlite_backend import SqliteBackend

        # Same real-model probe as above: package-import alone passes on
        # offline CI while encode falls back to difflib and the assert fails.
        if emb._get_model() is None:
            pytest.skip("real embedding model unavailable (offline / not vendored)")

        be = SqliteBackend(conn=migrated_conn)
        nodes = [
            GraphNode(
                uid="code:function:e.py::embed_text",
                kind="function",
                label="embed_text",
                file_path="e.py",
                start_line=1,
                signature="def embed_text(text: str) -> bytes",
                doc_blob="Encode a single string into a vector embedding.",
            ),
            GraphNode(
                uid="code:function:e.py::embed_texts",
                kind="function",
                label="embed_texts",
                file_path="e.py",
                start_line=10,
                signature="def embed_texts(texts: list) -> list",
                doc_blob="Batch-encode many strings into vector embeddings.",
            ),
            GraphNode(
                uid="code:function:e.py::render_table",
                kind="function",
                label="render_table",
                file_path="e.py",
                start_line=20,
                signature="def render_table(rows) -> str",
                doc_blob="Render rows as an ASCII table for the terminal.",
            ),
        ]
        be.bulk_upsert(nodes, [])

        # Persist an embedding for every seeded node (keyed on graph_nodes.id).
        for n in nodes:
            row = migrated_conn.execute(
                "SELECT id, signature, doc_blob FROM graph_nodes WHERE uid = ?", (n.uid,)
            ).fetchone()
            text = " ".join(filter(None, [n.label, row[1], row[2]]))
            emb.upsert_embedding(migrated_conn, "graph_nodes", row[0], text)
        migrated_conn.commit()

        graph._BACKEND_SINGLETON = be
        monkeypatch.setattr(graph, "_backend", lambda *, backend=None: be)
        try:
            res = graph.cos_graph_similar(
                "code:function:e.py::embed_text", confidence_min=0.0, top_k=5
            )
        finally:
            graph._BACKEND_SINGLETON = None

        data = _assert_ok(res)
        assert data["meta"]["scorer"] == "persisted-embeddings"
        uids = [r["uid"] for r in data["results"]]
        # root excluded; the near-twin (embed_texts) ranks above the unrelated one.
        assert "code:function:e.py::embed_text" not in uids
        assert "code:function:e.py::embed_texts" in uids
        assert uids[0] == "code:function:e.py::embed_texts"
