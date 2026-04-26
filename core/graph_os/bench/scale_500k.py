"""500k-symbol benchmark harness (Phase I.13).

PURPOSE:  Generate a large deterministic fixture corpus and drive
          `run_benchmark` against it so §8.5 scale targets get
          replaced by measured numbers in `docs/benchmarks/graph_os.md`.
INPUT:    --count N (default 500_000) and optional --output path.
OUTPUT:   JSON report file plus stdout summary.
DEPENDS:  graph_os.bench.fixtures + harness, SqliteBackend (or Kuzu
          via COS_GRAPH_BACKEND=kuzu).
NOTES:    Writes files in sharded directories to avoid ballooning a
          single folder. Deterministic: same --count reproduces the
          exact same byte-identical files (P-I-11).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve()
_CORE_DIR = _HERE.parent.parent.parent
_TOS_DIR = _CORE_DIR / "thinking_os"
for _p in (_CORE_DIR, _TOS_DIR):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def _build_shard(shard_dir: Path, *, start: int, count: int) -> list[Path]:
    shard_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i in range(start, start + count):
        target = shard_dir / f"m_{i:07d}.py"
        body = (
            f"# generated fixture {i}\n"
            f"def fn_{i:07d}(x: int) -> int:\n"
            f"    \"\"\"deterministic body\"\"\"\n"
            f"    return x + {i}\n\n"
            f"class Thing{i}:\n"
            f"    def run(self, n: int) -> int:\n"
            f"        return fn_{i:07d}(n)\n"
        )
        target.write_text(body, encoding="utf-8")
        paths.append(target)
    return paths


def generate_corpus(root: Path, *, count: int, shard_size: int = 2000) -> list[Path]:
    """Produce `count` files split across shard directories."""
    produced: list[Path] = []
    for shard_index in range((count + shard_size - 1) // shard_size):
        shard_start = shard_index * shard_size
        shard_count = min(shard_size, count - shard_start)
        shard_dir = root / f"shard_{shard_index:04d}"
        produced.extend(_build_shard(shard_dir, start=shard_start, count=shard_count))
    return produced


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=500_000)
    parser.add_argument("--corpus-dir", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--limit-for-dryrun", type=int, default=None)
    args = parser.parse_args()

    import shutil
    import tempfile

    from db import init_db  # type: ignore
    from graph_os.backends.sqlite_backend import SqliteBackend  # type: ignore
    from graph_os.bench import run_benchmark  # type: ignore

    count = args.limit_for_dryrun or args.count
    corpus_root = (
        Path(args.corpus_dir)
        if args.corpus_dir
        else Path(tempfile.mkdtemp(prefix="cos-bench-500k-"))
    )
    print(f"[bench] generating {count} files under {corpus_root} ...")
    gen_started = time.monotonic()
    paths = generate_corpus(corpus_root, count=count)
    gen_elapsed = int((time.monotonic() - gen_started) * 1000)
    print(f"[bench] generated {len(paths)} files in {gen_elapsed} ms")

    db_path = Path(tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)
    conn = init_db(str(db_path))
    backend = SqliteBackend(conn=conn)

    print("[bench] running benchmark ...")
    bench_started = time.monotonic()
    result = run_benchmark(backend, paths)
    bench_elapsed = int((time.monotonic() - bench_started) * 1000)

    report = {
        "corpus_size": len(paths),
        "generation_duration_ms": gen_elapsed,
        "benchmark_duration_ms": bench_elapsed,
        "index_duration_ms": result.index_duration_ms,
        "query_duration_ms": result.query_duration_ms,
        "nodes_written": result.nodes_written,
        "edges_written": result.edges_written,
        "backend": result.backend_id,
        "hardware": {
            "uname": os.uname().sysname if hasattr(os, "uname") else "unknown",
            "cpu_count": os.cpu_count(),
        },
    }
    conn.close()

    if args.output:
        Path(args.output).write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )
    print(json.dumps(report, indent=2, default=str))

    if args.cleanup:
        shutil.rmtree(corpus_root, ignore_errors=True)
        db_path.unlink(missing_ok=True)
        print(f"[bench] cleaned up {corpus_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
