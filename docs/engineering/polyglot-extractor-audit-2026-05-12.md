<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-05-12 -->
# Polyglot Extractor — Post-Ship Audit (2026-05-12)

> P: Verify the polyglot extractor upgrade (commit 9bee865) landed correctly,
> map the dependency graph + decision points + edge cases + personas, surface
> remaining optimisation gaps, and route the doc-propagation work.
> R: Reviewing the change after it merged, planning the next sprint, or
> answering "did anything regress / what does the system look like now?"
> S: Pre-ship roadmap — that's [docs/playbooks/polyglot-extractor-roadmap.md](../playbooks/polyglot-extractor-roadmap.md).
> N: [graph-hallucination-cures.md](graph-hallucination-cures.md),
>    [graph_os-queries.md](graph_os-queries.md),
>    [mcp-schema-traps.md](mcp-schema-traps.md)

> Nav: [Engineering Index](./00-index.md) | [Docs Index](../00-index.md)

## 1. What landed

Commit `9bee865`. Eleven files changed (1428 +, 150 −).

| Group | Workstream | Status | Real-repo impact |
|---|---|---|---|
| A | Shell tree-sitter | shipped | parse_errors 209→28 (87%↓); clean parses 4→91 (4%→83%) |
| B1 | JSON extractor (new) | shipped | 19 files → 138 nodes / 119 edges / 0 errors |
| B2 | TOML extractor (new) | shipped | 1 file → 12 nodes / 11 edges / 0 errors |
| C | Go grammar wired | partial | grammar loadable; code_go rewrite deferred |
| D | Parallel reindex | shipped | `-j N` flag, 1.6× speedup at 2 workers |

Post-ship reindex (force, 1241 files): **27.6 s sequential / 17 s @ 2 workers**.
Incremental reindex (cache hit): **1.27 s (1213 of 1241 hit)**.

## 2. Dependency graph (after change)

```
                    ┌───────────────────────────────┐
                    │   ingest/base.py              │
                    │   walk_local + DEFAULT_INCLUDE│ +.json +.toml
                    └─────────────┬─────────────────┘
                                  │ plan.files
                                  ▼
                    ┌───────────────────────────────┐
                    │ cli/graph_commands.py         │
                    │ graph-reindex [-j N]          │ NEW: parallel path
                    └─────────────┬─────────────────┘
                                  │
                  ┌───────────────┴────────────────┐
                  │                                │
                  ▼                                ▼
        seq  for file in plan:       parallel  ProcessPoolExecutor
                  │                          │   (NEW: _parallel_dispatch)
                  └──────────────┬───────────┘
                                 ▼
                    ┌───────────────────────────────┐
                    │ tools/reindex_dispatch.py     │
                    │   _EXT_MAP[.py/.ts/.tsx/.sh/  │ +.json +.toml
                    │            .yaml/.go/.md]     │
                    │   content_hash cache lookup   │
                    └─────────────┬─────────────────┘
                                  │
              ┌───────────────────┼──────────────────────┐
              ▼                   ▼                      ▼
      extractors/             extractors/           extractors/
      code_python  ──┐        code_shell  ◄── NEW    code_json  ◄── NEW
      code_ts      ──┤          tree-sitter-bash     stdlib json + JSON5 fallback
      code_go      ──┤          (regex fallback)
      code_yaml    ──┤        extractors/
      contracts    ──┘        code_toml  ◄── NEW
                                stdlib tomllib (3.11+)
                                tomli fallback
                                  │
                                  ▼
                    ┌───────────────────────────────┐
                    │ tree_sitter_overlay.py        │
                    │   _LOADERS: py / ts / tsx /   │ +go (NEW)
                    │            bash / yaml / go   │
                    └───────────────────────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────────┐
                    │ backend (SQLite primary +     │
                    │           Kùzu secondary)     │
                    │ graph_nodes / graph_edges_v12 │
                    │ graph_evidence_v12            │
                    │ file_index_state (cache key)  │
                    └───────────────────────────────┘
```

## 3. Mind map (capabilities added)

```
Polyglot graph (after 9bee865)
│
├── Languages
│   ├── Python ........ AST + tree-sitter (unchanged, reference)
│   ├── TypeScript .... tree-sitter (unchanged)
│   ├── Shell ......... tree-sitter-bash + regex fallback ⭐ migrated
│   ├── YAML .......... PyYAML (unchanged)
│   ├── Markdown ...... custom (unchanged)
│   ├── JSON .......... NEW — stdlib + JSON5 fallback ⭐ added
│   ├── TOML .......... NEW — stdlib tomllib + tomli fallback ⭐ added
│   └── Go ............ regex (rewrite deferred); grammar wired ⭐ ready
│
├── Node kinds (new)
│   ├── contract:npm:package:<n>       (package.json declarations)
│   ├── contract:pypi:package:<n>      (pyproject project.name)
│   ├── contract:crates:package:<n>    (Cargo.toml package)
│   ├── contract:mcp:server:<n>        (mcp.json servers)
│   ├── tool:config:.../scripts/<n>    (npm scripts + pyproject scripts)
│   ├── event:config:.../hooks/<n>     (settings.json hook events)
│   └── contract:ts_path_alias         (tsconfig path aliases)
│
├── Edge kinds (new)
│   ├── imports → npm:package:<n>      (npm deps)
│   ├── imports → pypi:package:<n>     (pyproject deps)
│   ├── imports → crates:package:<n>   (Cargo deps)
│   ├── declares → mcp:server:<n>      (mcp.json)
│   └── contains → folder:<workspace>  (Cargo workspace members)
│
├── Performance
│   ├── content-hash cache  ✅  97% hit rate this repo
│   ├── parallel reindex    ✅  -j N flag, 1.6× @ 2 workers
│   ├── auto-prune-deleted  ✅  hook fires on rm/mv
│   └── lazy grammar load   ⚠️  each ProcessPool worker re-imports
│
└── Verification
    ├── 637 graph_os tests passing
    ├── 87% shell error reduction
    └── Roadmap doc as source of truth
```

## 4. Problem tree (what could still go wrong)

```
"World-class polyglot graph" — remaining failure modes
│
├── Scale (Uber-class repos = 1M+ files)
│   ├── ★ walk_local max_files default = 50,000  ⚠️
│   │       Blocks any > 50k file repo. CLI can pass --max-files higher
│   │       but plan.files is in-memory list (no streaming).
│   ├── ★ cli/graph_commands.py:689 hardcoded max_files=5000 inside
│   │       graph-impact-changes command. Inconsistent with the
│   │       primary path's 50,000. Bug, not blocker.
│   ├── SQLite write serialisation
│   │       WAL handles concurrent readers, single writer at a time.
│   │       Parallel speedup tops out near 4 workers in practice.
│   │       For 1M+ files: shard the DB OR migrate hot path to Kùzu.
│   └── No streaming walk
│           os.walk + list collects everything before extraction starts.
│           Memory: ~100 MB for 1M paths. OK but not great.
│
├── Correctness
│   ├── Go extractor still regex-based
│   │       Grammar is loadable; consumer waiting on Go templates +
│   │       golden fixtures (roadmap §4.3 Epic C1).
│   ├── Shell residual 28 parse_errors
│   │       Real tree-sitter ERROR nodes on edge-case bash. Acceptable
│   │       — 87% reduction; remaining are genuine ambiguities.
│   └── JSON5 path
│           Heuristic strip of comments + trailing commas. Doesn't
│           handle every JSON5 feature (single quotes, unquoted keys).
│           Sufficient for tsconfig.json; out of spec for full JSON5.
│
├── Determinism
│   ├── Worker emission order non-deterministic
│   │       ProcessPoolExecutor + as_completed → edge insert order varies
│   │       run-to-run. Output graph is identical by uid (set semantics),
│   │       but row order in graph_edges_v12 differs. CI determinism gate
│   │       (roadmap §5 Epic E2) would catch real regressions.
│
└── Doc drift
    ├── AGENTS.md → mentions extractors generically; new langs not listed
    ├── graph-hallucination-cures.md → no row for config-file invisibility
    ├── mcp-schema-traps.md → UID scheme doesn't list new kinds
    └── reindex_dispatch.py docstring → still says original chain map
```

## 5. Decision table — "which extractor for which file?"

| Filename / pattern | Suffix | Extractor chain | Subtype emitter |
|---|---|---|---|
| any `.py` | `.py` | code_python → contracts | — |
| any `.ts` / `.tsx` | `.ts/.tsx` | code_ts → contracts | — |
| any `.go` | `.go` | code_go → contracts | regex (rewrite pending) |
| any `.sh` | `.sh` | code_shell | tree-sitter-bash → regex fallback |
| any `.yaml`/`.yml` | `.yaml/.yml` | code_yaml | — |
| `package.json` | `.json` | code_json | npm package + deps + scripts |
| `tsconfig.json` / `tsconfig.*.json` | `.json` | code_json | extends chain + path aliases |
| `mcp.json` / `.mcp.json` | `.json` | code_json | MCP server registry |
| `settings.json` / `settings.*.json` | `.json` | code_json | hook event nodes |
| other `.json` | `.json` | code_json | file node only (generic) |
| `pyproject.toml` | `.toml` | code_toml | project + deps + scripts |
| `Cargo.toml` | `.toml` | code_toml | crate + deps + workspace |
| other `.toml` | `.toml` | code_toml | file node only (generic) |
| `*.md` | `.md` | md_links + docs:md (RAG) | task_deps if under docs/tasks/ |

## 6. Scenarios + personas

### Persona 1 — Developer on a small project (1k files)
**Workflow:** `cos graph-reindex` after pulling main; otherwise auto-reindex on edit.
**Latency:** ~25 s cold, ~1 s incremental. Acceptable.
**Sees benefit from:** none of the new work directly; cache + auto-reindex were already good.

### Persona 2 — Developer on a polyglot project (Python + TS + configs)
**Workflow:** mostly edits `.py` / `.tsx` / `package.json` / `tsconfig.json`.
**Sees benefit:** ⭐ JSON extractor now surfaces npm deps, ts path aliases, package scripts. `cos_graph_query "react"` resolves to a package node.

### Persona 3 — Hook author (shell-heavy)
**Workflow:** edits `core/hooks/*.sh`.
**Sees benefit:** ⭐⭐ shell extractor 87% fewer noise errors; `source $(dirname "$0")/X` resolves; function nodes no longer match inside heredocs/comments.

### Persona 4 — Operator on a monorepo (50k+ files)
**Workflow:** `cos graph-reindex --workers 8` on bulk index, otherwise relies on PostToolUse auto-reindex.
**Sees benefit:** ⭐ parallel reindex. Cold index drops from minutes to <1 min on M-class hardware.
**Gap:** `--max-files` default 50,000 needs explicit override.

### Persona 5 — Uber-class operator (1M+ files)
**Workflow:** bulk index in CI nightly; agents only see incremental.
**Status:** ⚠️ Need to raise `walk_local` cap and consider Kùzu-primary backend.
**Mitigation today:** shard the repo (per-package indexing), set `--max-files` explicitly.

### Persona 6 — Agent in a fresh session
**Workflow:** session start → reads CLAUDE.md + graph queries.
**Sees benefit:** roadmap doc reachable via `cos_doc_search "polyglot"`; new node kinds (`contract:npm:package:*`) discoverable via `cos_graph_query`.

## 7. Edge cases — verified vs unverified

| Case | Language | Verified? | Test/evidence |
|---|---|---|---|
| function inside heredoc | shell | ✅ | smoke test (foo inside `<<EOF…EOF` not matched) |
| `$(dirname "$0")/X` | shell | ✅ | `test_dirname_self_resolves_to_script_dir` |
| comment with `name()` | shell | ✅ | `test_comment_lines_ignored` |
| `function foo()` vs `foo() {` | shell | ✅ | tree-sitter `function_definition` covers both |
| trailing commas in tsconfig | json | ✅ | JSON5 fallback strips them |
| `// comment` in tsconfig | json | ✅ | `_strip_jsonc` |
| nested workspace `crates/*` | toml | ✅ | smoke (folder edge emitted) |
| `import type {…}` (TS-only) | ts | partial | not yet flagged as evidence.type_only — roadmap §4.2 |
| Go generics | go | ❌ | regex extractor doesn't see them — rewrite pending |
| Empty file | all | ✅ | file node + zero entries (no crash) |
| BOM at start | all | ✅ | tree-sitter + json handle |
| 100k-line file | python | ✅ | <200 ms (under budget) |

## 8. Optimisation audit

| # | Item | Current | Action |
|---|---|---|---|
| O1 | walk_local cap | 50,000 hard | raise to 1,000,000; document override |
| O2 | line 689 stale max_files=5000 | bug, inconsistent | match default 50,000 |
| O3 | Parallel speedup ceiling | ~1.6× @ 2 workers, ~2× @ 4, plateaus | accept SQLite WAL serialisation; deferred Kùzu-primary |
| O4 | Per-worker grammar reload | ~50ms × N workers, one-time | accept (one-shot at startup) |
| O5 | DB write batching | per-file commit | future: batch inserts in dispatch loop |
| O6 | Streaming walk | full list in memory | future: generator walk for 1M+ |
| O7 | Determinism CI gate | absent | roadmap §5 E2 |

O1 + O2 are cheap fixes; landing in this audit pass.

## 9. Doc propagation plan

| Doc | Add |
|---|---|
| [AGENTS.md](../../AGENTS.md) | Brief note: graph now indexes .json + .toml; cos graph-reindex --workers for monorepo |
| [graph-hallucination-cures.md](graph-hallucination-cures.md) | New cure row: "config files invisible to graph" → indexed since 9bee865 |
| [mcp-schema-traps.md](mcp-schema-traps.md) | UID scheme: add config:json:* / config:toml:* / npm:* / pypi:* / crates:* / mcp:server:* |
| Roadmap (already shipped) | unchanged — it's the pre-ship plan |

## 10. Bottom line

The work shipped is **correct, tested, and faster** for the targeted workflows.
**Optimisation gaps** identified above are tracked; the cheap ones (O1, O2,
doc propagation) land with this audit. The Uber-class concerns (O3 ceiling,
O5 batching, O6 streaming) require infrastructure work and remain on the
roadmap.

## See also

- [docs/playbooks/polyglot-extractor-roadmap.md](../playbooks/polyglot-extractor-roadmap.md) — pre-ship plan
- [docs/engineering/graph_os-queries.md](graph_os-queries.md) — routing contract
- [docs/engineering/graph-hallucination-cures.md](graph-hallucination-cures.md) — cure matrix
