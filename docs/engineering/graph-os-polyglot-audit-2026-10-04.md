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
- [ ] **F-02 [CRITICAL] The toolchain context was never switched on.**
  `toolchain.set_active()` has no production caller, although its docstring says
  dispatch calls it, so tsconfig `paths` / `baseUrl`, `go.mod` and pyproject
  package roots never reached an extractor. On Dana, 296 `@/…` alias imports and
  1,007 `@dana/*` workspace-package imports pointed at invented
  `code:module:npm:…` packages, so editing `packages/core` surfaced no dependent
  app. (Fix tracked with the TypeScript and Go resolution items below.)
- [x] **F-03 [MEDIUM] Parallel indexing failed files on a write race.**
  `graph-reindex -j 4` on Dana logged `UNIQUE constraint failed: graph_nodes.uid`
  and 94–151 per-file failures that a retry pass had to recover. `upsert_node` did
  a bare INSERT after an existence check, so a sibling worker inserting the same
  shared uid (a stub, a folder) in between failed the file; `upsert_edge` opened a
  deferred `BEGIN`, whose read-to-write upgrade fails at once under contention —
  `busy_timeout` never applies to it. Fix: `INSERT … ON CONFLICT(uid) DO NOTHING`
  then re-read, and `BEGIN IMMEDIATE` for edges. Test:
  `test_upsert_node_survives_a_rival_insert_of_the_same_uid`. Measured on Dana `-j 4`:
  first-pass failures 94–151 → 0, wall time 176 s → 84 s at a similar load.
- [x] **F-04 [HIGH] Renamed or deleted TypeScript symbols lived on as zombies.**
  The reindex prune was scoped to each extractor module's `EXTRACTOR_ID`, but
  `code_ts` stamps its AST declarations `code_ts_ts@v1` (and `code_python` its
  tree-sitter imports `code_python_ts@v1`), so a renamed `foo` kept its node and a
  deleted call kept its `calls` edge — 3,087 nodes and 24,141 edges on Dana sat
  outside every prune. Fix: `types.extractor_family()` derives the full ID set
  (sub-extractors and older versions) from the provenance registry. Test:
  `test_ts_rename_and_removed_call_leave_no_zombies`. Reported by the
  completeness auditor.
- [x] **F-05 [MEDIUM] A `$schema` URL silently voided a whole tsconfig.** Both
  JSONC strippers (`toolchain`, `code_json`) deleted `//[^\n]*` without knowing
  about strings, so `"$schema": "https://json.schemastore.org/tsconfig"` was cut at
  `https:` and the file stopped parsing — every alias in it was dropped, and
  `code_json` lost the file's keys whenever it also had a comment. Fix: one
  string-aware `toolchain.strip_json_comments`, used by both. Test:
  `test_schema_url_survives_comment_stripping`.
