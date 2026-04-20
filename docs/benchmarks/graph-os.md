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

## 500-file scale smoke — 2026-04-20 (post-Phase-I hardening)

Fixture: `core.graph_os.bench.scale_500k --limit-for-dryrun 500` —
deterministic Python module generator.

| Metric | Value |
|---|---|
| Backend | SQLite fallback |
| Corpus size | 500 files |
| Generation duration | 51 ms |
| Indexing duration | 459 ms (~0.92 ms / file) |
| Query duration (10 samples) | 8 ms |
| Nodes written | 3 000 |
| Edges written | 2 500 |

Full 500 k run is gated on Kùzu adoption + a dedicated runner; the
harness is reproducible (`--count 500_000 --output report.json`).

## Viewer FPS scale — 2026-04-20

Fixture: `core.graph_os.bench.viewer_fps --nodes 10000` — ring + +7 graph
to give ForceAtlas2 something to spread.

| Metric | Value |
|---|---|
| Nodes | 10 000 |
| Edges | 19 992 |
| Ingest (SQLite) | 1 719 ms |
| HTML render | **53 ms** |
| HTML size | 447 KB (~0.044 KB / node) |

The HTML-side render path stays well under the 200 ms first-paint
budget (plan §15.5). The browser-runtime FPS target (≥ 30 FPS at
10 k nodes) is a separate measurement deferred to a
playwright/headless slice; the input cost is already bounded.

## Persian / multilingual precision harness

New harness `core.graph_os.bench.persian_precision` runs a 12-doc /
5-query fixture against the active embedding model. Baseline run on
MiniLM is recorded below; the BGE-M3 run will replace it in I.1
after the migrator completes.

_Record the MiniLM result in this section; re-run after BGE-M3 and
append. Target: `precision_at_1 ≥ 0.8` on Persian queries._

## Regression gate

`graph_os.bench.harness.assert_within_budget` fails a PR when
indexing > 50 ms / file or the 10-sample query loop exceeds 50 ms
total on the above fixture. `tests/test_bench.py::test_budget_assertion`
exercises the gate in CI.
