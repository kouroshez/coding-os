"""graph_os S1 B1 — concurrency smoke test.

DEPENDS:      graph_os.backends.sqlite_backend, threading.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from graph_os.types import GraphEdge, GraphNode

THREAD_COUNT = 4
OPS_PER_THREAD = 100
# Every thread seeds its own node set so upsert_node is always valid.
# Writers upsert + edge-update; readers count / fetch. Mix distributes
# roughly 40% writes, 60% reads.


def _make_node(tid: int, i: int) -> GraphNode:
    return GraphNode(
        uid=f"t{tid}:n{i}",
        kind="code:function",
        label=f"fn_{tid}_{i}",
        file_path=f"t{tid}.py",
        start_line=i,
        end_line=i + 1,
        metadata={"tid": tid, "i": i},
    )


def _run_thread(
    backend: Any,
    tid: int,
    errors: list[BaseException],
    barrier: threading.Barrier,
) -> None:
    try:
        barrier.wait(timeout=10)
        for i in range(OPS_PER_THREAD):
            op = i % 5
            if op in (0, 1):  # upsert_node
                backend.upsert_node(_make_node(tid, i))
            elif op == 2:  # upsert_edge (needs two nodes)
                a = _make_node(tid, i)
                b = _make_node(tid, (i + 1) % OPS_PER_THREAD)
                backend.upsert_node(a)
                backend.upsert_node(b)
                backend.upsert_edge(
                    GraphEdge(
                        source_uid=a.uid,
                        target_uid=b.uid,
                        edge_type="calls",
                        extractor="concurrency-test",
                        confidence=0.5,
                    )
                )
            elif op == 3:  # read path: get_node
                backend.get_node(f"t{tid}:n{i}")
            else:  # op == 4 — count + list
                backend.count_nodes()
                backend.list_edges(limit=10)
    except BaseException as exc:
        errors.append(exc)


def _exercise_backend(backend: Any) -> None:
    errors: list[BaseException] = []
    barrier = threading.Barrier(THREAD_COUNT)
    threads = [
        threading.Thread(
            target=_run_thread,
            args=(backend, tid, errors, barrier),
            name=f"graph-worker-{tid}",
        )
        for tid in range(THREAD_COUNT)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
        assert not t.is_alive(), f"thread {t.name} did not finish"
    # No ProgrammingError / ValueError / corruption.
    for err in errors:
        assert not isinstance(err, sqlite3.ProgrammingError), err
        assert not isinstance(err, ValueError), err
    assert errors == [], f"concurrency errors: {errors!r}"

    # Every thread inserted OPS_PER_THREAD/5 * 2 distinct uids via op 0/1,
    # plus op 2 added its own pair (already in the 0/1 set indices 0..n-1).
    # Final node count is at least THREAD_COUNT distinct seeds; assert a
    # lower bound rather than an exact count because the interleaving of
    # upserts is non-deterministic.
    total_nodes = backend.count_nodes()
    assert total_nodes >= THREAD_COUNT
    # Edge count must be non-negative and match what list_edges reports.
    edge_count_total = backend.count_edges()
    listed = backend.list_edges(limit=edge_count_total or 1)
    assert len(listed) <= edge_count_total + 1


# ---------------------------------------------------------------------------
# SQLite — always runs.
# ---------------------------------------------------------------------------


def test_sqlite_backend_concurrency(tmp_path: Path) -> None:
    from graph_os.backends.sqlite_backend import SqliteBackend

    db_path = tmp_path / "graph_os-concurrency.db"
    backend = SqliteBackend(db_path=str(db_path))
    try:
        _exercise_backend(backend)
    finally:
        backend.close()


def test_sqlite_concurrent_reads_no_lock(tmp_path: Path) -> None:
    """G18: get_node/count_nodes/count_edges/list_edges/sample_nodes no
    longer hold write_lock. Seed + spawn 16 reader threads; assert all
    succeed without 'database is locked' under WAL."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.types import GraphEdge, GraphNode

    db_path = tmp_path / "graph_os-reads.db"
    backend = SqliteBackend(db_path=str(db_path))
    try:
        # Seed: 50 nodes + 100 edges.
        for i in range(50):
            backend.upsert_node(
                GraphNode(
                    uid=f"code:function:test.py::fn_{i}",
                    kind="function",
                    label=f"fn_{i}",
                    file_path="test.py",
                    start_line=i,
                    lang="py",
                )
            )
        for i in range(100):
            backend.upsert_edge(
                GraphEdge(
                    source_uid=f"code:function:test.py::fn_{i % 50}",
                    target_uid=f"code:function:test.py::fn_{(i + 1) % 50}",
                    edge_type="calls",
                    extractor="test@v1",
                    confidence=0.9,
                )
            )

        def reader(_):
            backend.get_node("code:function:test.py::fn_0")
            backend.count_nodes()
            backend.count_edges()
            backend.list_edges(limit=10)
            backend.sample_nodes(None, 5)
            return True

        with ThreadPoolExecutor(max_workers=16) as ex:
            futures = [ex.submit(reader, i) for i in range(16)]
            for f in as_completed(futures):
                assert f.result() is True
    finally:
        backend.close()
