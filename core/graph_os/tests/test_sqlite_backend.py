"""SqliteBackend unit tests — write path, read path, idempotency.

Covers the Section 21 ship checklist for I.0: every backend operation
round-trips correctly and is safe to call twice. Parity with Kuzu is
asserted separately in test_backend_parity.py.
"""

from __future__ import annotations

import pytest

# conftest pushes core/thinking-os + core onto sys.path.
from graph_os.types import EvidenceSignal, GraphEdge, GraphNode  # noqa: E402
from graph_os.backends.sqlite_backend import SqliteBackend  # noqa: E402


@pytest.fixture()
def backend(migrated_conn):
    return SqliteBackend(conn=migrated_conn)


def _make_node(uid: str, *, kind: str = "code:function", label: str = "fn") -> GraphNode:
    return GraphNode(
        uid=uid,
        kind=kind,
        label=label,
        file_path=f"fake/{uid}.py",
        start_line=1,
        end_line=10,
        signature=f"def {label}() -> None",
        lang="py",
        doc_blob=f"docstring for {label}",
        ast_hash=f"ast:{uid}",
        content_hash=f"ct:{uid}",
        metadata={"arity": 0, "is_public": True},
    )


def test_upsert_node_inserts_then_updates(backend):
    node = _make_node("code:function:a")
    first_id = backend.upsert_node(node)

    # Second call with same uid but different label updates in place.
    updated = _make_node("code:function:a", label="fn_renamed")
    second_id = backend.upsert_node(updated)
    assert first_id == second_id

    fetched = backend.get_node("code:function:a")
    assert fetched is not None
    assert fetched.label == "fn_renamed"
    assert fetched.metadata == {"arity": 0, "is_public": True}


def test_get_node_returns_none_for_unknown_uid(backend):
    assert backend.get_node("code:function:missing") is None


def test_upsert_edge_requires_both_endpoints(backend):
    with pytest.raises(ValueError):
        backend.upsert_edge(
            GraphEdge(
                source_uid="missing:src",
                target_uid="missing:dst",
                edge_type="calls",
                extractor="test",
            )
        )


def test_upsert_edge_round_trip_with_evidence(backend):
    backend.upsert_node(_make_node("code:function:a"))
    backend.upsert_node(_make_node("code:function:b"))
    edge = GraphEdge(
        source_uid="code:function:a",
        target_uid="code:function:b",
        edge_type="calls",
        extractor="test",
        confidence=0.75,
        source_span="fake/a.py:5-8",
        evidence=(
            EvidenceSignal("same_scope", 0.5, "local lookup"),
            EvidenceSignal("explicit_import", 0.25, None),
        ),
    )
    edge_id = backend.upsert_edge(edge)
    assert edge_id > 0

    fetched = backend.list_edges(source_uid="code:function:a", include_evidence=True)
    assert len(fetched) == 1
    fetched_edge = fetched[0]
    assert fetched_edge.target_uid == "code:function:b"
    assert fetched_edge.edge_type == "calls"
    assert fetched_edge.confidence == pytest.approx(0.75)
    assert fetched_edge.source_span == "fake/a.py:5-8"
    assert len(fetched_edge.evidence) == 2
    assert {sig.signal_name for sig in fetched_edge.evidence} == {
        "same_scope",
        "explicit_import",
    }


def test_upsert_edge_is_idempotent(backend):
    backend.upsert_node(_make_node("code:function:a"))
    backend.upsert_node(_make_node("code:function:b"))
    edge = GraphEdge(
        source_uid="code:function:a",
        target_uid="code:function:b",
        edge_type="calls",
        extractor="test",
        confidence=0.5,
        evidence=(EvidenceSignal("same_scope", 0.5),),
    )
    first = backend.upsert_edge(edge)
    second = backend.upsert_edge(edge)
    assert first == second
    assert backend.count_edges() == 1
    # Evidence replaced wholesale, so we still have exactly the new signals.
    edges = backend.list_edges(include_evidence=True)
    assert len(edges[0].evidence) == 1


def test_upsert_edge_re_resolution_replaces_evidence(backend):
    backend.upsert_node(_make_node("code:function:a"))
    backend.upsert_node(_make_node("code:function:b"))
    first = GraphEdge(
        source_uid="code:function:a",
        target_uid="code:function:b",
        edge_type="calls",
        extractor="test",
        confidence=0.5,
        evidence=(EvidenceSignal("same_scope", 0.5),),
    )
    backend.upsert_edge(first)
    second = GraphEdge(
        source_uid="code:function:a",
        target_uid="code:function:b",
        edge_type="calls",
        extractor="test",
        confidence=0.95,
        evidence=(
            EvidenceSignal("lsp_overlay", 0.45, "pyright"),
            EvidenceSignal("same_scope", 0.5),
        ),
    )
    backend.upsert_edge(second)

    edges = backend.list_edges(include_evidence=True)
    assert len(edges) == 1
    assert edges[0].confidence == pytest.approx(0.95)
    assert len(edges[0].evidence) == 2
    assert {sig.signal_name for sig in edges[0].evidence} == {
        "lsp_overlay",
        "same_scope",
    }


def test_delete_node_cascades(backend):
    backend.upsert_node(_make_node("code:function:a"))
    backend.upsert_node(_make_node("code:function:b"))
    backend.upsert_edge(
        GraphEdge(
            source_uid="code:function:a",
            target_uid="code:function:b",
            edge_type="calls",
            extractor="test",
        )
    )
    assert backend.count_edges() == 1

    assert backend.delete_node("code:function:a") is True
    assert backend.count_edges() == 0
    assert backend.delete_node("code:function:a") is False


def test_bulk_upsert_returns_counts(backend):
    nodes = [_make_node(f"code:function:f{i}") for i in range(5)]
    edges = [
        GraphEdge(
            source_uid=nodes[i].uid,
            target_uid=nodes[i + 1].uid,
            edge_type="calls",
            extractor="test",
            confidence=0.5 + 0.1 * i,
        )
        for i in range(4)
    ]
    node_count, edge_count = backend.bulk_upsert(nodes, edges)
    assert (node_count, edge_count) == (5, 4)
    assert backend.count_nodes(kind="code:function") == 5
    assert backend.count_edges(edge_type="calls") == 4


def test_list_edges_confidence_min_prunes(backend):
    backend.upsert_node(_make_node("code:function:a"))
    backend.upsert_node(_make_node("code:function:b"))
    backend.upsert_node(_make_node("code:function:c"))
    backend.upsert_edge(
        GraphEdge(
            source_uid="code:function:a",
            target_uid="code:function:b",
            edge_type="calls",
            extractor="t",
            confidence=0.2,
        )
    )
    backend.upsert_edge(
        GraphEdge(
            source_uid="code:function:a",
            target_uid="code:function:c",
            edge_type="calls",
            extractor="t",
            confidence=0.9,
        )
    )
    high = backend.list_edges(source_uid="code:function:a", confidence_min=0.5)
    assert len(high) == 1
    assert high[0].target_uid == "code:function:c"

    all_edges = backend.list_edges(source_uid="code:function:a", confidence_min=0.0)
    assert len(all_edges) == 2
    # Ordered by confidence DESC.
    assert all_edges[0].target_uid == "code:function:c"


def test_list_edges_filter_by_edge_types(backend):
    backend.upsert_node(_make_node("code:function:a"))
    backend.upsert_node(_make_node("code:function:b"))
    backend.upsert_edge(
        GraphEdge(
            source_uid="code:function:a",
            target_uid="code:function:b",
            edge_type="calls",
            extractor="t",
        )
    )
    backend.upsert_edge(
        GraphEdge(
            source_uid="code:function:a",
            target_uid="code:function:b",
            edge_type="imports",
            extractor="t",
        )
    )
    only_calls = backend.list_edges(edge_types=["calls"])
    assert [e.edge_type for e in only_calls] == ["calls"]


def test_confidence_out_of_range_rejected_at_construction():
    with pytest.raises(ValueError):
        GraphEdge(
            source_uid="a",
            target_uid="b",
            edge_type="calls",
            extractor="t",
            confidence=1.5,
        )
    with pytest.raises(ValueError):
        GraphEdge(
            source_uid="a",
            target_uid="b",
            edge_type="calls",
            extractor="t",
            confidence=-0.1,
        )
