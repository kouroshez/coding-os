"""Scale benchmark fixtures + regression gate (I.13).

The bench module is intentionally small: it generates fixture corpora
of configurable size, runs the indexer + a set of read queries against
the backend, and records the measured numbers in a machine-readable
shape that `docs/benchmarks/graph_os.md` pulls in.
"""

from .fixtures import build_mixed_corpus, build_python_corpus
from .harness import BenchResult, run_benchmark

__all__ = [
    "BenchResult",
    "build_mixed_corpus",
    "build_python_corpus",
    "run_benchmark",
]
