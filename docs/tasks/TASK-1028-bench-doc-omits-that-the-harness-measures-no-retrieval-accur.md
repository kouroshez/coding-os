---
id: TASK-1028
title: "Bench doc omits that the harness measures no retrieval accuracy"
swimlane: docs
kind: docs
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-31
started: 2026-08-31
completed: 2026-08-31
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-1028: Bench doc omits that the harness measures no retrieval accuracy

**Outcome (one sentence):** The published token-cost claim states plainly that no retrieval-accuracy metric was measured, so a reader cannot mistake a cost result for a quality result.

## Read First
- docs/engineering/third-party-token-bench.md
- README.md
- src/core/graph_os/bench/third_party.py

`ProbeRow` in src/core/graph_os/bench/third_party.py emits `graph_tokens`,
`baseline_tokens` and `savings_pct` and nothing else. There is no accuracy, recall or
precision field anywhere in the harness, and it has never been run against a
code-retrieval benchmark.

The existing "Honest limits" section lists five caveats, all about how the *cost* was
estimated (chars/4, probe selection, the grep window, corpus size, --ref pinning).
None of them says the harness measures no answer quality. A reader of README.md
line 549 or AGENTS.md line 103 sees "75-82% cheaper" with no statement that cheaper
was the only axis measured.

Raised on r/LocalLLaMA (2026-08-31, top comment on the post, score 4) naming
CodeRAG-Bench, CoIR-Retrieval, ContextBench and SWE-Explore-Bench. The critique is
correct and was conceded publicly. Running one of those benchmarks is a separate,
much larger task; this one closes the honesty gap in what is already published.


## Work Log
- 2026-08-31 [claude]: Added the missing limit to the bench doc (cost is the only measured axis; named the three ProbeRow fields and the…
- 2026-08-31 [claude]: commit 0bd390aca5 — test(matrix): assert every --extra group in the matrix exists in pyproject
- 2026-08-31 [claude]: commit 8cc3c1c5e8 — docs(bench): state that the token benchmark measures no retrieval accuracy
- 2026-08-31 [claude]: Status transitioned to complete via cos task-done.
