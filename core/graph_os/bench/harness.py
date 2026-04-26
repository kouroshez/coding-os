"""Benchmark harness (I.13).

PURPOSE:  Measure indexer throughput + read-path latency on fixture
          corpora. Results feed `docs/benchmarks/graph_os.md` and the
          regression gate.
INPUT:    backend + fixture paths.
OUTPUT:   BenchResult (JSON-friendly).
DEPENDS:  extractors, backend, stdlib time.
NOTES:    The gate is enforced by `assert_within_budget`.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from ..backend import GraphBackend
from ..extractors import code_python, md_links, contracts


@dataclass
class BenchResult:
    corpus_size: int
    index_duration_ms: int
    query_duration_ms: int
    nodes_written: int
    edges_written: int
    backend_id: str
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def run_benchmark(
    backend: GraphBackend,
    files: Iterable[Path],
    *,
    query_samples: int = 10,
) -> BenchResult:
    """Index the given files and time a small read-path sample."""
    file_list = list(files)
    t0 = time.monotonic()
    nodes_total = 0
    edges_total = 0
    for path in file_list:
        suffix = path.suffix.lower()
        source = path.read_text(encoding="utf-8")
        for extractor in _extractors_for(suffix):
            result = extractor(str(path), source)
            n, e = backend.bulk_upsert(result.nodes, result.edges)
            nodes_total += n
            edges_total += e
    index_ms = int((time.monotonic() - t0) * 1000)

    t1 = time.monotonic()
    for _ in range(query_samples):
        backend.list_edges(limit=50)
    query_ms = int((time.monotonic() - t1) * 1000)

    return BenchResult(
        corpus_size=len(file_list),
        index_duration_ms=index_ms,
        query_duration_ms=query_ms,
        nodes_written=nodes_total,
        edges_written=edges_total,
        backend_id=backend.backend_id,
    )


def assert_within_budget(
    result: BenchResult,
    *,
    per_file_budget_ms: float = 50.0,
    per_query_budget_ms: float = 50.0,
    query_samples: int = 10,
) -> None:
    """Raise AssertionError when a run exceeds the regression budget."""
    if result.corpus_size == 0:
        return
    avg_index_ms = result.index_duration_ms / result.corpus_size
    avg_query_ms = result.query_duration_ms / max(query_samples, 1)
    assert avg_index_ms <= per_file_budget_ms, (
        f"indexing regressed: {avg_index_ms:.1f} ms/file > {per_file_budget_ms}"
    )
    assert avg_query_ms <= per_query_budget_ms, (
        f"query regressed: {avg_query_ms:.1f} ms/query > {per_query_budget_ms}"
    )


def _extractors_for(suffix: str):
    if suffix == ".py":
        return (code_python.extract, contracts.extract)
    if suffix == ".md":
        return (md_links.extract,)
    return ()


__all__ = ["BenchResult", "run_benchmark", "assert_within_budget"]
