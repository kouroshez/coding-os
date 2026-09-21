---
id: TASK-1037
title: "Graph benchmark has no accuracy oracle; LSP call hierarchy can supply one"
swimlane: infra
kind: feature
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-09-15
started: 2026-09-20
completed: 2026-09-20
agent_session: ses-claude-20260920-211122-bc06
depends_on: []
blocked_by: []
references: []
---
# TASK-1037: Graph benchmark has no accuracy oracle; LSP call hierarchy can supply one

**Outcome (one sentence):** The published graph benchmark reports a recall number beside savings_pct from the same run, so a cheaper retrieval can no longer be mistaken for a better one.

## Read First
- docs/engineering/third-party-token-bench.md
- src/core/graph_os/bench/third_party.py
- src/core/graph_os/bench/persian_precision.py

ProbeRow emits graph_tokens, baseline_tokens, savings_pct and nothing else. The
Honest limits section now says so, which closed the honesty gap but not the
measurement one.

Four readers on r/LLMDevs (2026-09-14) worked the problem out in the thread. The
usable conclusions, in the order they were reached:

- CodeRAG-Bench, CoIR-Retrieval, ContextBench and SWE-Explore-Bench all treat a
  chunk as the retrieval unit. A caller is a node. Chunk relevance does not map
  onto "did it find every caller", so none of the four answers this question.
- Extracting ground truth by walking the AST of SWE-bench patches grades the
  graph against a second syntax walk. Both go blind in the same places, so recall
  reads clean exactly where it is not.
- An oracle has to resolve types. A language server's call hierarchy
  (textDocument/prepareCallHierarchy + callHierarchy/incomingCalls) returns an
  exact caller set per symbol on the same repos the harness already clones, so
  precision and recall are computable per probe in the same run that produces
  savings_pct.
- Dynamic dispatch defeats the oracle as well as the graph. Those probes must be
  scored in a separate bucket, or one number mixes "the graph is wrong" with
  "nothing static could have found it".

persian_precision.py already computes precision_at_1 / precision_at_3 for a
different corpus, so the scoring half has a shape to copy rather than invent.


## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a probe symbol in a cloned target repo
  **When** the benchmark runs
  **Then** ProbeRow carries the oracle's caller set size, the graph's recall against it, and a bucket label separating statically-resolvable probes from dynamic ones.
- **Given** a probe whose callers are reached only through dynamic dispatch
  **When** recall is aggregated
  **Then** it is reported in its own bucket and excluded from the headline figure.
- **Given** the benchmark doc publishes a savings figure
  **When** a reader reads that table
  **Then** a recall figure from the same run sits beside it.
- **Given** the oracle is unavailable for a language
  **When** the harness runs on that repo
  **Then** it records "no oracle" rather than a recall of zero or a silent omission.

## Work Log
- 2026-09-21 [claude]: Edit _oracle.py
- 2026-09-21 [claude]: Edit _oracle.py
- 2026-09-21 [claude]: Edit third_party.py
- 2026-09-21 [claude]: Edit test_bench_honesty.py
- 2026-09-21 [claude]: commit 0d8748b784 — test(scheduled): split the nightly tests at the maintenance seam
- 2026-09-21 [claude]: Built the oracle, and the build corrected the design twice. jedi over pyright/LSP as planned, but not as an…
- 2026-09-21 [claude]: commit a3f54608bf — feat(bench): grade reference accuracy with a jedi oracle beside the savings figure
- 2026-09-21 [claude]: Status transitioned to complete via cos task-done.
