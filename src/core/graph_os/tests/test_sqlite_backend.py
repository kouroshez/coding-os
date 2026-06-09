"""SqliteBackend unit tests — write path, read path, idempotency.

Covers the Section 21 ship checklist for I.0: every backend operation
round-trips correctly and is safe to call twice. Parity with Kuzu is
asserted separately in test_backend_parity.py.
"""

from __future__ import annotations

import pytest

from graph_os.backends.sqlite_backend import SqliteBackend

# conftest pushes core/thinking_os + core onto sys.path.
from graph_os.types import EvidenceSignal, GraphEdge, GraphNode


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


def test_upsert_edge_drops_self_loops(backend):
    """F12 / Audit #3: extractors sometimes emit edges where
    source_uid == target_uid (mis-resolved recursion). Backend rejects
    them with rc=-1 so doctor's self-loop bucket stays empty post-
    reindex."""
    backend.upsert_node(_make_node("code:function:self"))
    edge = GraphEdge(
        source_uid="code:function:self",
        target_uid="code:function:self",
        edge_type="calls",
        extractor="test",
        confidence=0.5,
    )
    rc = backend.upsert_edge(edge)
    assert rc == -1
    assert backend.count_edges() == 0


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


def _raw_edge_rows(conn, source_uid: str, target_uid: str, edge_type: str) -> int:
    return conn.execute(
        """
        SELECT COUNT(*) FROM graph_edges_v12 e
        JOIN graph_nodes s ON s.id = e.source_id
        JOIN graph_nodes t ON t.id = e.target_id
        WHERE s.uid=? AND t.uid=? AND e.edge_type=?
        """,
        (source_uid, target_uid, edge_type),
    ).fetchone()[0]


def test_upsert_contains_dedups_across_extractors(backend, migrated_conn):
    """W6.10: the folder spine is re-emitted by every extractor that
    touches a file. `contains` edges must dedup on (source,target) regardless
    of `extractor`, else a file seen by N extractors yields N raw rows that
    inflate degree centrality (which counts COUNT(e.id), not DISTINCT)."""
    backend.upsert_node(_make_node("folder:pkg", kind="folder", label="pkg"))
    backend.upsert_node(_make_node("code:file:pkg/a.py", kind="code:file", label="a.py"))
    for ex in ("code_python@v1", "contracts@v1", "task_deps@v1"):
        backend.upsert_edge(
            GraphEdge(
                source_uid="folder:pkg",
                target_uid="code:file:pkg/a.py",
                edge_type="contains",
                extractor=ex,
                confidence=1.0,
            )
        )
    assert _raw_edge_rows(migrated_conn, "folder:pkg", "code:file:pkg/a.py", "contains") == 1


def test_upsert_non_contains_keeps_per_extractor_rows(backend, migrated_conn):
    """Control for the W6.10 dedup: only `contains` collapses across
    extractors. Other edge types keep their per-extractor provenance row
    (UNIQUE is on source,target,type,extractor)."""
    backend.upsert_node(_make_node("code:function:a"))
    backend.upsert_node(_make_node("code:function:b"))
    for ex in ("extractor_one", "extractor_two"):
        backend.upsert_edge(
            GraphEdge(
                source_uid="code:function:a",
                target_uid="code:function:b",
                edge_type="calls",
                extractor=ex,
                confidence=0.5,
            )
        )
    assert _raw_edge_rows(migrated_conn, "code:function:a", "code:function:b", "calls") == 2


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


# ---------------------------------------------------------------------------
# Hard-delete contract (TASK-295) — the graph mirrors HEAD-of-tree; removed
# symbols are deleted, NOT tombstoned. These tests pin the doc to the code.
# ---------------------------------------------------------------------------


def _file_node(uid: str, file_path: str) -> GraphNode:
    return GraphNode(
        uid=uid,
        kind="code:function",
        label=uid.rsplit(":", 1)[-1],
        file_path=file_path,
        start_line=1,
        end_line=2,
        lang="py",
    )


def test_delete_nodes_for_file_hard_deletes(backend, migrated_conn):
    backend.upsert_node(_file_node("code:function:foo.py::a", "foo.py"))
    backend.upsert_node(_file_node("code:function:foo.py::b", "foo.py"))
    backend.upsert_node(_file_node("code:function:bar.py::c", "bar.py"))

    deleted = backend.delete_nodes_for_file("foo.py")
    assert deleted == 2
    # foo.py nodes are GONE (not soft-marked); bar.py untouched.
    assert backend.get_node("code:function:foo.py::a") is None
    assert backend.get_node("code:function:bar.py::c") is not None
    # idempotent — a second delete removes nothing.
    assert backend.delete_nodes_for_file("foo.py") == 0


def test_graph_nodes_has_no_deleted_at_column(migrated_conn):
    """No tombstone column exists — proves the hard-delete contract is real,
    not the soft-delete the old skill doc claimed."""
    cols = {row[1] for row in migrated_conn.execute("PRAGMA table_info(graph_nodes)").fetchall()}
    assert "deleted_at" not in cols


def test_skill_doc_matches_hard_delete_reality():
    """The graph-os-authoring SSOT must not claim tombstoning (doc≠code drift
    was the bug). It must state the hard-delete contract instead."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[4]
    skill = repo_root / "src/templates/meta/skills/graph-os-authoring/SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "tombstoned, not deleted" not in text
    assert "HARD-deleted" in text
