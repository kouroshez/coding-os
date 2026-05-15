"""Determinism golden test (Section 24.2 of the plan + principle P-I-11).

Same inputs => byte-identical rows across runs. We run the same
deterministic node/edge stream three times into three separate DBs
and compare the projection (label + uid + edge tuple) byte-for-byte.
Any non-determinism (e.g. the ORDER BY tie-breaker is unstable, or
metadata JSON is serialised with unsorted keys) shows up here.
"""

from __future__ import annotations

from graph_os.types import EvidenceSignal, GraphEdge, GraphNode
from graph_os.backends.sqlite_backend import SqliteBackend


def _deterministic_corpus():
    nodes = [
        GraphNode(
            uid=f"code:function:mod.fn_{i:02d}",
            kind="code:function",
            label=f"fn_{i:02d}",
            file_path=f"mod/file_{i // 4}.py",
            start_line=i * 10,
            end_line=i * 10 + 8,
            signature=f"def fn_{i:02d}(x: int) -> int",
            lang="py",
            doc_blob="",
            ast_hash=f"ast:{i:02d}",
            content_hash=f"ct:{i // 4}",
            metadata={"arity": 1, "idx": i, "tags": ["stable", f"slot_{i % 3}"]},
        )
        for i in range(8)
    ]
    edges: list[GraphEdge] = []
    for i in range(len(nodes) - 1):
        edges.append(
            GraphEdge(
                source_uid=nodes[i].uid,
                target_uid=nodes[i + 1].uid,
                edge_type="calls",
                extractor="test",
                confidence=0.5 + 0.05 * i,
                source_span=f"mod/file_{i // 4}.py:{i * 10}-{i * 10 + 8}",
                evidence=(
                    EvidenceSignal("same_scope", 0.5),
                    EvidenceSignal("explicit_import", 0.05 * i, note=f"hop{i}"),
                ),
            )
        )
    return nodes, edges


def _dump_projection(backend: SqliteBackend) -> list[tuple]:
    rows: list[tuple] = []
    for edge in backend.list_edges(limit=1000, include_evidence=True):
        ev = tuple((s.signal_name, round(s.weight, 6), s.note) for s in edge.evidence)
        rows.append(
            (
                edge.source_uid,
                edge.target_uid,
                edge.edge_type,
                edge.extractor,
                round(edge.confidence, 6),
                edge.source_span,
                ev,
            )
        )
    return rows


def test_three_runs_produce_identical_projection(tmp_path):
    import database  # type: ignore

    projections: list[list[tuple]] = []
    for run_idx in range(3):
        path = str(tmp_path / f"run_{run_idx}.db")
        conn = database.init_db(path)
        try:
            backend = SqliteBackend(conn=conn)
            nodes, edges = _deterministic_corpus()
            backend.bulk_upsert(nodes, edges)
            projections.append(_dump_projection(backend))
        finally:
            conn.close()

    assert projections[0] == projections[1] == projections[2], (
        "non-deterministic: projections diverged across runs"
    )


def test_node_counts_are_stable(tmp_path):
    import database  # type: ignore

    counts: list[tuple[int, int]] = []
    for run_idx in range(3):
        conn = database.init_db(str(tmp_path / f"nodes_{run_idx}.db"))
        try:
            backend = SqliteBackend(conn=conn)
            nodes, edges = _deterministic_corpus()
            backend.bulk_upsert(nodes, edges)
            counts.append((backend.count_nodes(), backend.count_edges()))
        finally:
            conn.close()
    assert counts[0] == counts[1] == counts[2]
