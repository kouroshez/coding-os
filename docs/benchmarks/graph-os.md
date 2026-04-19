<!-- domain:ALL | layer:benchmark | ssot:true | updated:2026-04-19 -->
# graph-os Benchmarks

**Purpose.** Replace the extrapolated scale targets in
[phase-i-knowledge-graph-plan.md §8.5](../phase-i-knowledge-graph-plan.md)
with measured numbers. Append-only — new runs are added at the top so
the history is preserved.

**Hardware baseline.** MacBook Pro M1 / 16 GB — the reference machine
for all Phase I measurements. Different hardware adds a multiplier
footnote; it does not replace the row.

---

## Smoke run — 2026-04-19 (commit: pre-commit HEAD)

Fixture: `graph_os.bench.build_python_corpus(count=100)` — 100 stable
Python modules with chained imports + one class + one function each.

| Metric | Value |
|---|---|
| Backend | SQLite fallback |
| Corpus size | 100 files |
| Indexing duration | **105 ms** (~1.05 ms / file) |
| Query duration (10 samples) | **1 ms** (~0.1 ms / query) |
| Nodes written | 798 |
| Edges written | 698 |

### What this says about the §8.5 targets

§8.5 claims `<5 s` for 1 k files. Linear extrapolation from the 100-
file run (1.05 ms × 1 000 ≈ 1 s) easily clears that. §8.5 also claims
`<60 s` for 10 k files; same extrapolation gives ~10 s. The §8.5 bounds
are therefore comfortable on the SQLite fallback for the current
extractor set (I.4 Python + I.2 md_links + I.7 contracts).

### Gaps still to measure

- **10 k / 100 k / 500 k files.** Needs a bigger corpus builder; the
  shape of the indexer (`bulk_upsert` in SQLite) is linear in row
  count, so extrapolation should hold, but we capture measured
  numbers in the next run.
- **Kùzu backend.** Optional dep not installed in the smoke run —
  will re-measure once the `graph-os` extra is installed.
- **LSP overlay.** I.5 overlay is fake-driven; real pyright
  cold-start numbers will land in a follow-up run once the
  subprocess wiring ships (plan Section 7.4).

## Regression gate

`graph_os.bench.harness.assert_within_budget` fails a PR when
indexing > 50 ms / file or the 10-sample query loop exceeds 50 ms
total on the above fixture. `tests/test_bench.py::test_budget_assertion`
exercises the gate in CI.
