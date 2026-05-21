"""Micro-benchmarks for hot-path coding-os primitives.

Run:  make bench   (or: uv run pytest tests/bench/ -m bench --benchmark-only)

These are NOT correctness tests — they guard against latency
regressions on the operations that run on every hook invocation /
every retrieval call. Every test is marked `bench` so the normal
matrix sweeps skip them.

The graph_os subsystem has its own scale harness under
src/core/graph_os/bench/ (corpus-level index/query timing). This
file covers the cheap, always-on primitives that harness does not.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_CORE = Path(__file__).resolve().parent.parent.parent / "src" / "core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))
if str(_CORE / "thinking_os") not in sys.path:
    sys.path.insert(0, str(_CORE / "thinking_os"))

pytestmark = pytest.mark.bench


def test_bench_extract_concepts(benchmark):
    """Concept extraction runs on every memory write — must stay sub-ms."""
    from thinking_os.concepts import extract_concepts

    path = "src/backend/apps/orders/models/commission.py"
    result = benchmark(extract_concepts, file_path=path, domain="BACKEND")
    assert isinstance(result, list)
    assert result, "expected at least one concept"


def test_bench_init_db(benchmark, tmp_path):
    """Cold DB init happens on every fresh hook subprocess that needs state."""
    from thinking_os.database import init_db

    def _init():
        db = tmp_path / f"bench-{id(object())}.db"
        conn = init_db(db)
        conn.close()

    benchmark(_init)


def test_bench_parse_task_file(benchmark):
    """The Scrumban task parser runs on every `cos task-sync`."""
    from thinking_os.task_parser import parse_task_file

    fixture = (
        "<!-- domain:BACKEND | layer:task | ssot:true | updated:2026-05-21 -->\n"
        "# TASK-001: [BACKEND] Bench fixture\n\n"
        "Purpose: micro-benchmark fixture.\n\n"
        "## Goal\n\nParse this deterministically.\n\n"
        "## Read First\n\n- `docs/x.md`\n\n"
        "## Acceptance\n\n1. Given X, when Y, then Z.\n\n"
        "## Dependencies\n\n- TASK-000 — upstream\n"
    )
    result = benchmark(parse_task_file, fixture)
    assert result is not None
