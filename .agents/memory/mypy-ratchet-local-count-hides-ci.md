---
name: mypy-ratchet-local-count-hides-ci
description: A local mypy-ratchet PASS proves nothing near the baseline; CI (only --extra rag) counts more errors and blocked main and the release PR
metadata:
  node_type: memory
  type: feedback
  originSessionId: d93f4805-68e9-4b2d-907b-da3320d1fbf8
  modified: 2026-10-07T19:23:07.775Z
---

A local `make lint` mypy-ratchet PASS at 1077 < 1078 still turned main's CI red at 1090. CI installs only `--extra rag`, so modules that import graph_os deps lose their types and report more errors. The red lint gate then skipped every pytest job and blocked release PR #107 (2026-10-07).

**Why:** a laptop with the graph_os extra installed counts ~13–16 fewer errors than CI does.

**How to apply:** after adding typed code to graph_os or thinking_os, check the count in a venv built like CI (`uv sync --extra rag` only), or keep the local count at least ~16 below baseline. Related: [[verification-matrix-must-match-ci]], [[red-ci-gate-hides-a-backlog]].
