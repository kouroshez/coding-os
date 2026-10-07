---
name: pytest-piped-to-tail-hides-failures
description: "`pytest ... | tail` returns tail's exit code; a red suite read as green — log to a file and echo pytest's own $?"
metadata:
  node_type: memory
  type: project
  originSessionId: d93f4805-68e9-4b2d-907b-da3320d1fbf8
  modified: 2026-10-07T12:12:57.315Z
---

`nice uv run pytest src/core/graph_os/tests/ -q -x 2>&1 | tail -6` ended with exit 0 while the last line said `1 failed, 148 passed`, and the pulse even showed `test-graph_os=PASS`. The pipe's status is `tail`'s, so a background run's completion notice ("exit code 0") proves nothing.

**Why:** a failure that reads as a pass is the exact silent-green shape [[verification-matrix-must-match-ci]] warns about; it nearly let a broken extractor test ride into a commit (2026-10-07, GO-09).

**How to apply:** for any suite whose verdict matters, write `pytest ... > log 2>&1; echo "exit=$?"; tail -2 log` and read the `exit=` line, not the notification. Never trust `| tail` / `| grep` pipelines for pass/fail.
