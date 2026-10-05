<!-- domain:CORE | layer:engineering | ssot:false | updated:2026-10-04 -->
# Graph-OS Polyglot Audit — Go · TS · JS · Python · Shell (2026-10-04)

> P: Defect register + fix checklist from a deep audit of graph_os coverage for
>    Go, TypeScript, JavaScript, Python and Shell, and for the React Native, Go
>    Fiber, Astro and FastAPI frameworks.
> R: Fixing or reviewing an item below, or judging how complete the graph is for
>    one of these stacks.
> S: Authoring a new extractor from scratch — see
>    [polyglot-extractor-roadmap.md](../playbooks/polyglot-extractor-roadmap.md).
> N: [graph_os-queries.md](graph_os-queries.md),
>    [graph-hallucination-cures.md](graph-hallucination-cures.md),
>    [polyglot-extractor-roadmap.md](../playbooks/polyglot-extractor-roadmap.md)

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## Questions this audit answers

1. Is the graph tuned for these five languages and four frameworks?
2. Can it show that a shared module is duplicated somewhere?
3. Does every file, class, function and dependency reach the graph, and can the
   MCP tools return them?
4. When an agent edits a file, does the graph surface the files that depend on it?
5. Can it say how many files import a given library?
6. Can it show that something was missed — a name used but never imported or
   defined?
7. Is the graph complete: every file in the repo and the detail inside it?

## Method

Read-only auditors (one per language or framework, plus an external-practice
researcher) probed the extractors with adversarial fixtures and the live graph.
Every finding below was reproduced before it was listed. Fixes were made one per
commit on `main` by a single writer.

## Findings and checklist

Severity: **CRITICAL** — the graph answers confidently and wrongly, or misses most
callers for a language · **HIGH** — a whole category is missing · **MEDIUM** —
partial · **LOW** — noise.

- [x] **F-01 [CRITICAL] An edit to a file erased every edge other files held into
  it (all languages).** The per-file reindex deleted the file's nodes *before*
  re-extracting, and edges are `ON DELETE CASCADE`, so the re-inserted symbols came
  back with new row ids and no inbound `calls` / `imports` edges. Repro: `a.py`
  calls `b.f()`; edit `b.py`; `references(b.f)` drops from 2 inbound cross-file
  edges to 0 until a full reindex. Fix: clear only the file's outbound edges up
  front (`delete_edges_from_file`), upsert, then hard-delete the nodes the new pass
  no longer emits (`delete_nodes_for_file(keep_uids=…)`). Tests:
  `test_reindexing_callee_keeps_inbound_cross_file_edges`,
  `test_reindex_drops_edges_the_file_no_longer_emits`.
