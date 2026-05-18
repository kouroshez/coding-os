"""graph_os storage backends.

One implementation ships today:
  - SqliteBackend — primary store; embedded, zero-deps, reuses the
                    thinking_os DB. p99 < 30 ms on 5-hop traversal at
                    1M nodes with PRAGMA tuning + ANALYZE (benchmark
                    2026-05-18).

KuzuBackend was retired in commit 2026-05-18 after the same benchmark
showed SQLite was well within budget for every realistic consumer
scale. If a future workload exceeds 10M nodes, restore from git
history (path: src/core/graph_os/backends/kuzu_backend.py).
"""
