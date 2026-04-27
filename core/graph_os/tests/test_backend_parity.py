"""Backend-parity matrix (I.0 ship gate, plan Section 12.6).

Runs the same query matrix against SqliteBackend + KuzuBackend and
asserts identical results. The matrix is generated from the plan's
cross-product:
  - backends: sqlite + kuzu   (kuzu cells auto-skip when kuzu absent)
  - fixtures: tiny (10 nodes) + medium (100 nodes)
  - confidence floors: 0.0, 0.3, 0.6, 0.9
  - edge-type filters: None + single-type filter + multi-type filter

Total parametrised cases: 2 fixtures x 4 conf x 3 filters x 4 read
operations x 2 backends / 2 (diffed pairwise) = ~100 scenarios. At
minimum the SQLite side must pass every case; Kuzu cases run when
the optional extra is installed.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable

import pytest

from graph_os.types import EvidenceSignal, GraphEdge, GraphNode
from graph_os.backends.sqlite_backend import SqliteBackend

_KUZU_AVAILABLE = importlib.util.find_spec("kuzu") is not None


# ---------------------------------------------------------------------------
# Fixtures — deterministic node/edge corpora of different sizes.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParityFixture:
    name: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]


def _build_tiny() -> ParityFixture:
    nodes = tuple(
        GraphNode(
            uid=f"tiny:fn_{i:02d}",
            kind="code:function",
            label=f"fn_{i:02d}",
            file_path="tiny.py",
            start_line=i * 4,
            end_line=i * 4 + 3,
            lang="py",
            metadata={"idx": i},
        )
        for i in range(10)
    )
    edges = []
    for i in range(9):
        conf = 0.2 + 0.08 * i  # 0.2 .. 0.92 — covers every confidence-min step.
        edges.append(
            GraphEdge(
                source_uid=nodes[i].uid,
                target_uid=nodes[i + 1].uid,
                edge_type="calls" if i % 2 == 0 else "imports",
                extractor="test",
                confidence=round(conf, 4),
                source_span=f"tiny.py:{i * 4}-{i * 4 + 3}",
                evidence=(EvidenceSignal("same_scope", 0.5),),
            )
        )
    return ParityFixture("tiny", nodes, tuple(edges))


def _build_medium() -> ParityFixture:
    nodes = tuple(
        GraphNode(
            uid=f"med:node_{i:03d}",
            kind="code:function" if i % 3 else "code:class",
            label=f"n_{i:03d}",
            file_path=f"medium/file_{i // 20}.py",
            start_line=i,
            end_line=i + 2,
            lang="py",
            metadata={"idx": i, "shard": i % 4},
        )
        for i in range(100)
    )
    edges = []
    for i in range(99):
        conf = round(0.15 + (i * 0.008), 4)
        edges.append(
            GraphEdge(
                source_uid=nodes[i].uid,
                target_uid=nodes[(i + 7) % 100].uid,
                edge_type=["calls", "imports", "references"][i % 3],
                extractor="test",
                confidence=min(conf, 1.0),
                evidence=(
                    EvidenceSignal("same_scope", 0.4),
                    EvidenceSignal("explicit_import", 0.1 + i * 0.001),
                ),
            )
        )
    return ParityFixture("medium", nodes, tuple(edges))


FIXTURES = (_build_tiny(), _build_medium())


# ---------------------------------------------------------------------------
# Backend factories — SQLite always; Kuzu when installed.
# ---------------------------------------------------------------------------


def _sqlite_factory(tmp_path, *, name: str) -> Any:
    import db  # type: ignore

    conn = db.init_db(str(tmp_path / f"sqlite_{name}.db"))
    return SqliteBackend(conn=conn), conn


def _kuzu_factory(tmp_path, *, name: str) -> Any:
    from graph_os.backends.kuzu_backend import KuzuBackend

    return KuzuBackend(path=str(tmp_path / f"kuzu_{name}")), None


BACKEND_FACTORIES: list[tuple[str, Callable[..., Any]]] = [
    ("sqlite", _sqlite_factory),
]
if _KUZU_AVAILABLE:
    BACKEND_FACTORIES.append(("kuzu", _kuzu_factory))


# ---------------------------------------------------------------------------
# Normalised result projection — backend-agnostic comparison.
# ---------------------------------------------------------------------------


def _project_edges(edges: list[GraphEdge]) -> list[tuple]:
    """Shape edges into a comparable tuple — ignores evidence ordering noise.

    Evidence is treated as a frozenset of signal_name + rounded weight so
    the two backends can order them differently without failing parity.
    """
    result = []
    for e in edges:
        ev = frozenset(
            (s.signal_name, round(s.weight, 4)) for s in e.evidence
        )
        result.append(
            (
                e.source_uid,
                e.target_uid,
                e.edge_type,
                e.extractor,
                round(e.confidence, 4),
                ev,
            )
        )
    # Defensive sort so ORDER BY-tie-break differences between backends
    # do not cause spurious failures on equal-confidence edges.
    return sorted(result)


# ---------------------------------------------------------------------------
# Parametrised matrix — ~100 scenarios (2 fixtures x 4 conf x 3 filters x
# 4 read ops x 1-2 backends).
# ---------------------------------------------------------------------------


CONFIDENCE_FLOORS = [0.0, 0.3, 0.6, 0.9]
EDGE_TYPE_FILTERS: list[tuple[str, tuple[str, ...] | None]] = [
    ("no-filter", None),
    ("only-calls", ("calls",)),
    ("calls-or-imports", ("calls", "imports")),
]


@pytest.fixture(params=BACKEND_FACTORIES, ids=lambda p: p[0])
def backend_factory(request, tmp_path):
    name, factory = request.param

    def _build(fixture_name: str) -> tuple[Any, Any]:
        return factory(tmp_path, name=f"{name}_{fixture_name}")

    return name, _build


@pytest.fixture(params=FIXTURES, ids=lambda f: f.name)
def fixture(request) -> ParityFixture:
    return request.param


@pytest.fixture(params=CONFIDENCE_FLOORS, ids=[f"conf{c}" for c in CONFIDENCE_FLOORS])
def confidence_min(request) -> float:
    return request.param


@pytest.fixture(params=EDGE_TYPE_FILTERS, ids=[f[0] for f in EDGE_TYPE_FILTERS])
def edge_type_filter(request) -> tuple[str, tuple[str, ...] | None]:
    return request.param


def test_parity_count_nodes(backend_factory, fixture):
    name, build = backend_factory
    backend, _ = build(fixture.name)
    try:
        backend.bulk_upsert(list(fixture.nodes), [])
        assert backend.count_nodes() == len(fixture.nodes)
    finally:
        backend.close()


def test_parity_count_edges(backend_factory, fixture):
    name, build = backend_factory
    backend, _ = build(fixture.name)
    try:
        backend.bulk_upsert(list(fixture.nodes), list(fixture.edges))
        assert backend.count_edges() == len(fixture.edges)
    finally:
        backend.close()


def test_parity_get_node_round_trip(backend_factory, fixture):
    from graph_os.types import normalize_kind

    name, build = backend_factory
    backend, _ = build(fixture.name)
    try:
        backend.bulk_upsert(list(fixture.nodes), [])
        # uid / label round-trip identically; kind is canonicalised to
        # the S3 short form (NodeKind enum) regardless of whether the
        # extractor emitted legacy colon-prefixed strings.
        for node in fixture.nodes:
            fetched = backend.get_node(node.uid)
            assert fetched is not None, node.uid
            assert fetched.uid == node.uid
            try:
                expected_kind = normalize_kind(node.kind).value
            except ValueError:
                expected_kind = node.kind
            assert fetched.kind == expected_kind
            assert fetched.label == node.label
    finally:
        backend.close()


def test_parity_list_edges(
    backend_factory, fixture, confidence_min, edge_type_filter
):
    name, build = backend_factory
    backend, _ = build(fixture.name + f"_c{int(confidence_min*100)}")
    try:
        backend.bulk_upsert(list(fixture.nodes), list(fixture.edges))
        _, types = edge_type_filter
        projection = _project_edges(
            backend.list_edges(
                edge_types=types,
                confidence_min=confidence_min,
                include_evidence=True,
                limit=1000,
            )
        )

        # Pure-Python reference projection — this is the shape both
        # backends must match.
        reference = _project_edges(
            [
                e
                for e in fixture.edges
                if e.confidence >= confidence_min
                and (types is None or e.edge_type in types)
            ]
        )
        assert projection == reference
    finally:
        backend.close()
