---
name: one-heavy-process-at-a-time
description: Never fork background workers in a loop or overlap heavy suites; a MacBook Pro crashed from ~20 concurrent graph reindex workers on 2026-10-24
metadata:
  type: feedback
---

Run at most one heavy process at a time (a pytest suite, mypy, a reindex, golden capture), `nice -n 19`, and check free RAM and swap first. Never time or loop a hook that spawns a background worker: each run forks one more process.

**Why:** On 2026-10-24 I timed the new session-start graph catch-up hook about 20 times while a CLI suite and mypy were running. Each hook run forked a detached reindex worker (about 600 MB each), RAM and swap filled, and macOS, which has no OOM killer, crashed the whole machine. The user had asked many times for safe execution, so this was not a first warning.

**How to apply:** Before running anything, count what is already running (`ps`, `vm_stat`, `sysctl vm.swapusage`). Measure a hook that forks only once, with its background step disabled, and kill what it spawned. A hook that can fork must hold a per-project lock so concurrent sessions cannot stack workers. Related: [[pytest-piped-to-tail-hides-failures]].
