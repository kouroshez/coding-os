# Graph-OS Round 4 — Full Defect Register (2026-05-27)

Companion to [docs/tasks/audits/audit-graph-os-round4-2026-05-27.md](../tasks/audits/audit-graph-os-round4-2026-05-27.md). Full Round 4 defect register; pointer kept under 3K-token lint cap.

**Task:** TASK-037
**Trigger:** user exhaustive intent — "", " mcp server", "", "", community: UID click error, 954/339 orphan/stale figures from Hub UI.
**Scope (delta over Round 3):** verify W6.1-W6.6 + W6.21 actually landed; surface defects R3 missed; per-language extractor matrix; hub UI surface bugs; community: UID scheme gap; deep probe each cos_graph_* tool with malformed inputs.
**Methodology:** 4 parallel diagnostic subagents (per-language coverage, hub UI, 17-tool live probing, orphans/stales deep dive) + foreground SQL/MCP probes. All probes against live `.coding-os/coding-os.db` (37 756 nodes / 77 410 edges) at 2026-05-27.
**Prior:** Round 3 register catalogued 60 defects (T1-T12, X1-X12, B1-B17, C1-C3, F1-F14, N1-N4); 6 waves landed (W6.1, W6.2, W6.3, W6.6, W6.14, W6.21) + 1 partial (W6.5) + 1 with taxonomy bug (W6.7).

## Baseline (2026-05-27, post-W6.1-W6.6)

- nodes: **37 756** (+139 vs R3 baseline) · edges: **77 410** (+1 125)
- doctor `healthy=false` — **897 orphans** (-164 vs R3 → W6.5 partial) · **339 stale_paths** (was 386 in R3 → -47, but still load-bearing)
- uid schemes (9): `code, doc, folder, cos, task, npm, pypi, config, mcp` — **`community:` NOT a node-table scheme** (root of R4-N5/R4-01)
- node kinds top: doc_heading 8828 · doc_frontmatter 6374 · identifier 6250 · import_ 4748 · function 3614 · method 2450
- edge types: contains 35 491 · calls 24 969 · has_param_type 4 457 · imports **4 035 (W6.1 N2 fix landed — imports separate from calls now)** · links_to 2 198 · returns_type 1 752 · constructs 983 · dispatches 896 · field_of_type 793 · is_decorated_by 764 · read_next 471 · handles_tool 141 · cites_heading 108 · inherits_from 103 · declares 97 · handles_route 84 · awaits 36 · handles_event 19 · references_doc 11 · re_exports 2

## Wave-6 land verification (commits e20a49e..a14f6b5 since 2026-05-26)

| Wave | Commit | Verification (live MCP probe) | Status |
|---|---|---|---|
| **W6.1** N2 imports edge | afcfc62 | `imports` edge_type now 4 035 rows (separate from `calls` 24 969) | ✅ LANDED |
| **W6.2** bucket-aware shrinker | 0d29831 | `cos_graph_impact(file, depth=3)` returns `impacted_count: 90` (int, NOT stringified); `truncated_tiers: {context: {from:53, to:26}}` honest | ✅ LANDED |
| **W6.3** file-uid impact rollup | d6a8a65 | same probe: `expanded_from_file: true`; will_break tier aggregates symbol-level edges up to file uid | ✅ LANDED |
| **W6.4** path BFS exclude externals | adfc9fb | `edge.traversal_direction` field present (R3 T2 fix landed); BUT R4-12 confirms `__future__`/`typing` stub hubs STILL bridge unrelated paths — fix excludes `code:external:*` but not in-repo stub modules | ⚠️ PARTIAL |
| **W6.5** markdown commonmark | 1eccdff | `read_next` down to 471; stale_paths NOT recleaned (339); pre-existing nodes from old regex preserved by idempotent upsert (no DELETE) | ⚠️ PARTIAL (R4-N7) |
| **W6.6** communities member floor | 1a2b8a5 | `cos_graph_communities(top=3, max_members=3)` returns 3 × 3 (was 33×1 before) | ✅ LANDED |
| **W6.14** semantic_scope label | (folded into W6.3) | `cos_graph_impact` response shows `meta.semantic_scope: "transitive_depth_3"` | ✅ LANDED |
| **W6.21** regression tests | 8235b8b | `pytest src/core/graph_os/tests/` reportedly 686 pass | ✅ LANDED |

## Cross-cutting NEW root causes (R4)

1. **Silent fuzzy-fallback resolver hijack (R4-01)** — `cos_graph_impact("garbage")` returns `ok=true` with blast radius for unrelated `code:function:src/cli/brain_commands.py::brain_gc`. Same fuzzy resolver fires on `xyz` → arbitrary doc file. **Load-bearing wrong answer**: agent thinks it queried "garbage" but got a real symbol's impact. Fix: require uid-scheme prefix OR path-shaped input; reject bare identifiers. Collapses R4-01 (impact), implicit similar (R4-01 confirms same behavior in `cos_graph_similar`).

2. **Default `kinds` blind-spot for non-function nodes (R4-02)** — `cos_graph_references(class_uid)` with default kinds returns 0 callers; class has 35 `constructs` + 21 `contains` not in default list. Agent reads 0 → assumes symbol is dead. Fix: compute defaults per `node.kind` OR emit `meta.default_kinds_warning` when count=0 but other-kind edges exist.

3. **Silent param ignored across 6 tools (R4-03, R4-05, R4-08, R4-09, R4-16, R4-19, R4-26)** — `min_size=1000` accepted but never applied; `edge_types="__nonsense__"` returns 1 root + 0 edges silently; `limit=-1` silently unbounded in `cos_graph_query`; `q="A"` (sub-2-char) accepted in `cos_graph_resolve` (mismatch with `cos_graph_query`); `confidence_min=999` accepted; `kind="bogus"` accepted. Collapses 7 separate symptoms — same class of bug. **Fix:** shared `_validate_*` helpers in `_shared.py`; apply consistently across all list-returning + filter-accepting tools.

4. **Synthetic-id leak (R4-N5)** — `cos_graph_communities` emits `community:<sha1[:12]>` strings the UI treats as clickable UIDs; backend `cos_graph_context` rejects with canonical UID-scheme error. 0 community: nodes exist in `graph_nodes`. **Fix path:** Option A (cheap): UI skip click handler when `uid.startsWith('community:')`. Option B (correct): register communities as first-class `kind='community'` nodes + `member_of_community` edges + resolver accepts scheme.

5. **Reindex doesn't prune deleted-file nodes (R4-N7)** — W6.5 markdown commonmark extractor patched, but 339 stale doc_file/identifier nodes from old regex remain. Pre-existing 105 truly-deleted file nodes + 227 moved-file nodes + 7 malformed `../../` paths persist. Fix: `cos graph-reindex --prune-stale` mode OR doctor `fix=True` includes "delete stale" category.

6. **Dep-extraction taxonomy error (R4-N6)** — W6.7 X2/X9 partial: 44 npm + 31 pypi nodes exist but `kind='doc_external'` (category error — they're not docs). Need `kind='dependency'` or `kind='package'`. [project.optional-dependencies] arrays still under-covered.

## R4 defect register (26 new defects, R4-01 to R4-26 + R4-N5 to R4-N12)

### CRITICAL (2)

| ID | Tool | Symptom | Root cause | Fix |
|---|---|---|---|---|
| **R4-01** | impact/similar/(any uid-accepting) | Fuzzy-resolve silently picks first FTS match for non-uid-prefix input — `impact("garbage")` returns blast for `brain_gc`, `impact("xyz")` returns doc file context. Wrong-answer trust failure | Auto-resolve fallback designed for raw-path convenience does not require uid prefix OR path-shaped input | Tighten fallback: require `^(code:|doc:|folder:|cos:)` OR contains `/`/`.`. Reject bare identifiers. Emit `meta.resolved_from: "fuzzy_fallback"` on every fuzzy hit |
| **R4-02** | references | Default `kinds="calls,accesses_field,imports,references_doc"` returns 0 for any **class** node — `constructs` (test instantiations) is missing from default | Defaults hand-picked for function nodes; class needs `constructs` | Compute defaults per node.kind, OR emit `meta.default_kinds_warning` when 0+other-kind-out-edges present |

### HIGH (11)

| ID | Tool | Symptom | Fix |
|---|---|---|---|
| **R4-03** | communities | `min_size` silently ignored (probe min_size=1000 still returns 200 communities sized 29-269) | Wire min_size into post-Louvain filter |
| **R4-04** | communities | `top=-1` rejected, `min_size=-1, max_members=-1` silently accepted | Symmetric positive-int validation |
| **R4-05** | export | `edge_types="__not_an_edge_type__"` silently filters to nothing | Cross-check arg against known edge types; fail validation on typo |
| **R4-06** | ranking | `iterations=0` returns uniform-vector ranks with positive scores (looks real) | Validate `iterations >= 1`; bonus `meta.converged` |
| **R4-07** | trace | `max_steps=0` returns `steps=[]` with `walk_truncated=true` (never walked) | Validate `max_steps >= 1` |
| **R4-08** | query | `limit=-1` silently unbounded; `limit=0` empty | Match `cos_graph_references::limit>0` pattern across all list tools |
| **R4-09** | resolve | `q="A"` (sub-2-char) accepted (mismatches `cos_graph_query` which rejects) | Add `len(q)>=2` guard parity |
| **R4-10** | contracts | Duplicate sources per uid (production + test); `cos_graph` listed despite removal | Dedupe by uid keeping non-test; exclude `tests/*` sources by default; drop removed tools |
| **R4-11** | entrypoints | `top=100` returns `envelope_unshrinkable=true` + `tokens_estimated=8068` (exceeds MCP cap) | Extend W6.2 shrinker per-tool table to cover entrypoints |
| **R4-12** | path | `__future__`/`typing` stub hubs STILL bridge unrelated paths (T1 root cause persists — fix excluded `code:external:*` but not in-repo stub modules) | Extend T1 exclude list: `__future__, typing, typing_extensions, __init__` |
| **R4-13** | doctor | `fixable_categories: ["self_loops","stale_paths"]` lists self_loops (not currently an issue) + omits orphans (the dominant issue) | Reflect actual current-issue fixability, OR rename to `fix_will_apply_to` |

### MEDIUM (8)

| ID | Tool | Symptom | Fix |
|---|---|---|---|
| **R4-14** | cos_graph (removed) | Stub still registered → `tools/list` exports it, costs handshake slot, pollutes `contracts` listing | Delete the stub + `@mcp.tool` decorator |
| **R4-15** | query | `q="SqliteBackend test "` (mixed-script) → 0 results despite `SqliteBackend` alone returning 46 | FTS5 unicode_tokenizer ANDs all tokens; either split on script boundary or fall back to OR-query |
| **R4-16** | centrality | `kind="bogus_kind"` silently returns `[]` (same shape as "no high-deg nodes of this kind") | Validate kind enum OR emit `meta.known_kinds` |
| **R4-17** | communities | `top=5, max_members=10` returns `count=15` (inflated past request); `top_effective=15` while `top_requested=50` (BOTH inflated) | Cap count<=top_requested OR rename meta field |
| **R4-18** | rename_plan | `new_name == old_name` happily returns 36-callsite plan with `risk=high` | Validate `new_name != current label`; return `risk: "no_op"` |
| **R4-19** | impact | `confidence_min=999` silently filters everything (same shape as "no impact") | Validate `0.0 <= confidence_min <= 1.0` |
| **R4-20** | impact | `depth=-1` works as if depth=1; meta echoes `transitive_depth_-1` (nonsense scope) | Validate `depth >= 1` |
| **R4-21** | context | `depth=99` accepted verbatim; visit_limit=50 cap depth-agnostic; same summary shape as depth=2 | Cap depth at 4; emit `meta.requested_depth, delivered_depth, reason` |

### LOW (5)

| ID | Tool | Symptom | Fix |
|---|---|---|---|
| **R4-22** | export | At `max_nodes=3` returns 2 unrelated isolated nodes (no edges) | Require root_uid OR edge-density-aware sampling |
| **R4-23** | export (dot) | Labels containing `"` or `\` not escaped — risk for doc-heading labels with quotes | Escape `"`, `\`, newlines in DOT and Mermaid labels |
| **R4-24** | path | `walk_truncated=false, frontier_saturated=true` simultaneous (contradiction; T6 still surfaces) | Define `frontier_saturated` semantics or drop it |
| **R4-25** | doctor | stale_paths samples include `../../`-prefixed paths (X7 X3 root cause persists) | New category `malformed_uid_path` separate from `stale_paths`; fix=True can prune cleanly |
| **R4-26** | query | `confidence_min=999` silently ignored (filter not applied to result rows) | Apply filter OR drop the arg |

### Hub UI surface defects (R4-N5 .. R4-N12, from Agent B)

| ID | Sev | Layer | Symptom | Fix path |
|---|---|---|---|---|
| **R4-N5** | HIGH | hub UI + communities | `community:<sha1>` clickable in UI; backend rejects; full evidence chain in agent B output (communities.py:341 emit, useSigma.ts:249 click, /api/graph/context/:uid backend reject) | Short-term: UI guard in useSigma click. Long-term: register communities as first-class nodes |
| **R4-N6** | MEDIUM | extractor json/toml | Dep nodes (44 npm + 31 pypi) emitted with `kind=doc_external` (taxonomy error) | New `kind='dependency'`; verify [project.optional-dependencies] walked |
| **R4-N7** | MEDIUM | reindex/doctor | W6.5 fix landed but 339 pre-existing stale nodes preserved (227 moved + 7 malformed + ~105 deleted + ~105 golden-test sandboxes) | `cos graph-reindex --prune-stale` mode OR doctor `fix=True` extends to stale category |
| **R4-N8** | LOW | tool registry | `cos_graph` deprecation tombstone inflates "17 tools" claim | Remove stub after migration deadline OR document 17+1 count |
| **R4-N9** | LOW | doctor + UI | doctor `healthy=false` treats `code:external:unresolved:*` orphans (mostly stdlib refs) same as real orphans → inflates "attention" for expected noise | Separate `orphaned_external_unresolved` vs `orphaned_inrepo`; healthy=true if only externals orphan |
| **R4-N10** | LOW | UI doctor page | `Health: attention` label has zero user-facing explanation of category semantics / thresholds | Add hover tooltips + fix-suggestion column |
| **R4-N11** | LOW | api contract drift | NodeInspector.tsx:12-26 and ContextPanel.tsx:16-19 call same `/api/graph/context/:uid` but expect different shapes (`neighbours, spine` vs `node, edges_by_type`) | Canonical response shape; consolidate consumer types |
| **R4-N12** | INFO | repo hygiene | `.coding-os/.reindex-debounce-*` files have suffix containing `.go` etc. → trip `find -name "*.go"` false positives | Use sha hash in debounce filenames; strip extension |

## Cross-tool disagreement on 3 NEW symbols (extends F1/N2 pattern)

### Symbol A: `code:function:src/core/thinking_os/database.py::get_db_stats`

| Tool | Answer | N |
|---|---|---|
| references (default) | direct callers | 15 |
| rename_plan | call_sites | 15 (agreement) |
| impact depth=3 | will_break tier | 38 (impacted_count=82 total) |
| detect_changes on database.py | downstream_tasks=0, risk=high | n/a |
| `git grep -l get_db_stats` | files | 9 |

### Symbol B: `code:function:src/core/thinking_os/tools/_shared.py::ok` (the envelope helper)

| Tool | Answer | N |
|---|---|---|
| references (default) | direct callers | 27 |
| rename_plan | call_sites | 27 |
| impact depth=3 | will_break | impacted_count=43, tier=28 |
| `from ._shared import ok` grep | import sites | ~30+ |

**NEW finding:** rename_plan for the envelope helper `ok` misses every site that did `from ._shared import ok` but never invokes as `_shared.ok(...)` — confirms N2 pattern at a different surface. The extractor counts imports on the module, not function-level reference.

### Symbol C: SqliteBackend class (re-probe with full kinds)

| Tool | Default | Full kinds | N |
|---|---|---|---|
| references default | 0 | (R4-02) | 0 |
| references full | constructs,contains,calls,imports,has_param_type,is_decorated_by | 38 |
| context | edge_counts | 21 contains + 35 constructs + 1 has_param_type | 57 |
| impact depth=-1 (silent re-interp) | direct | 38 |
| impact depth=3 | transitive | impacted_count=120 |
| rename_plan | call_sites | 36 |
| similar top_k=100 | total_count | 199 |

Six tools, six different numbers, no uniform `semantic_scope` across all. R4-02 + R4-20 + R4-12 collapse a chunk.

## Per-language extractor matrix (Agent A + foreground SQL)

Meta-repo only (consumer projects under `/tmp` and `tests/golden/` excluded from this count).

| Language | Real files | Indexed | Coverage % | Node kinds | Score vs Python (100%) | Top 3 missing |
|---|---|---|---|---|---|---|
| Python (.py) | 786 | 456 | 58% (.venv/__pycache__ skipped) | function/method/class/variable/import_/identifier | **100%** baseline | — |
| Markdown (.md) | 2 252 | 1 083 | 48% | doc_file/heading/frontmatter | 85% | Commonmark AST (W6.5 partial); image refs; footnotes |
| TS/TSX | ~4 411 (incl. node_modules in `find` count) | 124 | 2.8% real coverage | function/class/interface | 42% | param/return type edges; JSX components as nodes; arrow function first-class |
| YAML | 321 | 55 | 17% | file/module + frontmatter | 60% | Generic K/V (by design); broader rule/skill emission |
| JSON | 1 015 (mostly lock) | 20 | 2% (correct) | config:json/npm:package | 40% | Verify [project.optional]; tsconfig paths; mcp.json registry |
| TOML | 6 | 1 | 17% | config:toml/pypi:package | 35% | .codex/*.toml whitelist (X11); [project.optional-dependencies] complete |
| Bash (.sh) | 915 (many runtime-generated) | 115 | 13% | function/module/file | 55% | hook variables as nodes; trap handlers; reduce 7× dedup (T7) |
| Go (.go) | **0 in meta-repo** (only false positives via `.coding-os/.reindex-debounce-*` — R4-N12) | 0 | n/a | (extractor exists for consumer projects, not exercised here) | n/a | — |

**Languages NOT supported** (no real files in meta-repo → defer): Dart, Swift, Java, Kotlin, C++, C, Rust. Add when consumer projects bring them.

### Per-language priority checklists

**TypeScript/TSX:**
1. Param/return type annotations as `has_param_type`/`returns_type` edges (regex insufficient; TASK-121 tree-sitter overlay)
2. JSX components as first-class `kind='component'`
3. Arrow functions = first-class function nodes
4. React hooks (`useX`) as kind='react_hook' or handles_tool

**Bash:**
1. Reduce 7× contains dedup (T7)
2. Hook variables (`$COS_*`) as declares/reads nodes
3. `bash -c` subprocess + `trap` handler edges

**Markdown:**
1. **Commonmark AST migration** (W6.5 finish — extractor patched, OLD NODES NOT PRUNED → R4-N7)
2. Image refs (`![alt](path)`) → references_doc
3. Footnotes + reference-style links
4. Auto-link (`<http://...>`)

**YAML:**
1. All registered rules emitted as `kind='rule'` nodes (currently sparse — only 17)
2. Hook registry pairs (event, matcher) as first-class edges (E8 partial)
3. Schema validation per stack.yaml / adapter.yaml at extract-time

**JSON:**
1. All package.json deps captured (currently partial — 44 npm nodes vs Agent A's claimed 43)
2. tsconfig paths → references_doc
3. `mcp.json` → `kind='mcp_server'`
4. R4-N6 taxonomy fix

**TOML:**
1. [project.optional-dependencies] groups
2. [tool.X] arbitrary nested tables
3. Whitelist `.codex/*.toml` (X11)
4. R4-N6 taxonomy fix

## Orphan/stale breakdown (Agent D, 956 orphans / 339 stale)

### Orphans (956 = 943 identifiers + 12 file + 1 doc_file)

| Sub-category | Count | Assessment | Action |
|---|---|---|---|
| `code:external:unresolved:*` (Python AST couldn't resolve stdlib + dynamic refs) | 433 | **Expected noise** | Suppress from health check |
| `code:external:*` other (in-repo refs to symbols not indexed OR deleted) | 483 | **Mixed** — some real (deleted symbols), some optional features | Selective audit; 3-4h |
| `cos:identifier:*` (skill/adapter reference singletons) | 27 | **Expected noise** | Suppress or link during extraction |
| Orphaned `file` nodes (golden test fixtures lacking CONTAINS) | 12 | **Real bug** | Delete (re-index recreates); `doc_tree.py` to investigate |
| Orphaned `doc:file:CLAUDE.md` (symlink) | 1 | Low | Filter symlinks or explicit REFERENCES edge |

### Stale_paths (339)

> **Correction (2026-05-28, TASK-038):** this table analysed the 339-count baseline. After reindex/prune the moved/deleted rows cleared; the *residual* ~93 are dominated by rendered-location relative-link FALSE POSITIVES (source docs under `src/core/{rules,skills,commands}/` + `src/templates/**` whose `../../docs/…` links resolve correctly only post-render). See [audit-graph-os-round4 § Stale-paths correction](../tasks/audits/audit-graph-os-round4-2026-05-27.md#stale-paths-correction-2026-05-28--task-038). Do NOT sweep these as doc-debt.

| Category | Count | Assessment | Action |
|---|---|---|---|
| Moved during refactor (same filename elsewhere) | 227 | **Real bug** | Update `file_path` OR delete + re-index; 2-3h |
| Truly deleted files (no same-named replacement) | ~105 | **Real bug** | Safe delete; 1-2h |
| Golden-test sandboxed doc trees (`tests/golden/codex_*/docs/...`) | ~105 (overlap with truly-deleted?) | **Unclear intent** | Decide: exclude golden dirs from extraction OR keep for audit |
| Malformed `../../` and `../_meta/` relative paths (X7 root cause) | 7 | **Real bug** | Normalize or delete; 30m |

### Top 5 actions to bring doctor to `healthy=true`

1. **Suppress expected-noise categories from health check** — `code:external:unresolved:*` + `cos:identifier:*` → ~460 orphans drop instantly. 30 minutes. Highest ROI.
2. **Fix moved-file paths** (227 stale → 0). 2-3 hours.
3. **Delete orphaned file/folder nodes** (12). 1 hour incl. re-index.
4. **Delete truly-deleted-file nodes** (~105). 1-2 hours.
5. **Normalize/delete `../../`-relative paths** (7). 30 minutes.

Total ~5-8 hours to reach genuinely-healthy doctor state with no noise.

## W6.7-W6.20 status check (R3 fix-checklist deltas)

| Wave | Status post-R4 probe | Notes |
|---|---|---|
| W6.7 (TOML/JSON deps) | ⚠️ PARTIAL — nodes exist `kind=doc_external` (R4-N6); 73 imports edges + 2 declares to deps; under-covered optional-deps | Needs taxonomy fix + complete walk |
| W6.8 (context depth honesty) | ❌ NOT LANDED — depth=99 echoed verbatim, visit_limit=50 still hard-cap (R4-21 = N4 re-confirmed) | |
| W6.9 (read-pool pragmas) | ❓ Not re-probed R4 | likely landed (commit a3ec6ba /review nits chore) |
| W6.10 (dedup folder contains) | ✅ LANDED (TASK-038, 2026-05-28) — cross-extractor `contains` deduped at upsert boundary + `duplicate_contains` doctor cleanup; 703 redundant rows removed | |
| W6.11 (similar scorer) | ❓ Not re-probed | |
| W6.12 (builtin TYPE_UIDS) | ❌ NOT LANDED — has_param_type 4 457 (43% still point to unresolved builtins per R3) | X8/X6 active |
| W6.13 (rename_plan buckets) | ❓ Not re-probed | depends on W6.1 |
| W6.14 (semantic_scope) | ✅ LANDED — `meta.semantic_scope: "transitive_depth_3"` confirmed | |
| W6.15-W6.20 polish | ❓ Not re-probed | |

## Verifications PASS (R4 — new)

1. Graph drift since R3: +139 nodes, +1 125 edges; orphans 1 061→897 (-164 — W6.5 partial heal).
2. `cos_graph_path` `edge.traversal_direction` field present (R3 T2 landed).
3. `cos_graph_impact` `truncated_tiers` honest (`{from:53, to:26}`).
4. `cos_graph_export` mermaid at small size: valid syntax (LR direction, edges with labels).
5. `cos_graph_entrypoints` finds main/cli/cmd_* across cli/, scripts/, hooks/_helpers/, templates/.
6. `cos_graph_communities` honest meta: `members_truncated` vs `envelope_truncated` distinct (T11 partial).
7. `cos_graph_doctor` schema invariants present (`fix_applied`, `fixed_count` set even on read-only).
8. Persian FTS5 body content: `q=""` → clean `ok=true, results=[]`, no FTS5 error (G14 holds).
9. `cos_graph_rename_plan` `risk` field correct (15 sites → medium; 36 sites → high).
10. `cos_graph_impact` `semantic_scope` field present on every response.

## Coverage statement (R4)

- 18/18 cos_graph_* tools enumerated (17 functional + 1 deprecation tombstone)
- 8 currently-extracted languages scored vs Python baseline
- 26 NEW probe-level defects (R4-01..R4-26) + 8 NEW hub UI/extractor defects (R4-N5..R4-N12) = **34 new defects**
- 6 W6 lands verified live; 1 partial (W6.5); 1 with taxonomy bug (W6.7); 3 not landed (W6.8, W6.10, W6.12 still active from R3)
- 4 parallel diagnostic subagents (A per-lang, B hub UI, C 17-tool probe, D orphans/stale) all returned
- 3 NEW symbols probed for cross-tool agreement — all show F1/N2 pattern persistence

## Round-4 totals (post-agents)

- **34 new defects**: R4-01..R4-26 (probe) + R4-N5..R4-N12 (hub UI/extractor/registry)
- Severity split: **2 CRITICAL** (R4-01 fuzzy-resolve hijack, R4-02 default-kinds blind-spot) · **11 HIGH** · **13 MEDIUM** · **8 LOW/INFO**
- **6 NEW cross-cutting root causes** that collapse 18+ surface defects:
  1. Silent fuzzy-fallback resolver hijack (R4-01)
  2. Default `kinds` blind-spot for non-function nodes (R4-02)
  3. Silent param ignored / out-of-range across 7 tools (R4-03, R4-05, R4-08, R4-09, R4-16, R4-19, R4-26)
  4. Synthetic-id leak via communities (R4-N5)
  5. Reindex idempotent-upsert preserves stale nodes (R4-N7)
  6. Dep-extraction taxonomy error (R4-N6)

## Recommended Wave-7 (R4 deltas — apply after Wave-6 closeout)

1. **W7.1 cross-cutting validator helpers in `_shared.py`** — `_validate_positive_int`, `_validate_uid_or_path`, `_validate_query_min_chars`, `_validate_confidence`, `_validate_kind`, `_validate_edge_type`. Apply across every `cos_graph_*` tool. Collapses R4-03, R4-04, R4-05, R4-06, R4-07, R4-08, R4-09, R4-16, R4-19, R4-20, R4-26.

2. **W7.2 fuzzy-resolve guard** — `cos_graph_impact/similar/(any uid-accepting)` require uid scheme OR path-shape; reject bare identifiers. Collapses R4-01 (CRITICAL).

3. **W7.3 default-kinds per node.kind** — `cos_graph_references` computes defaults by node kind; class nodes include `constructs`. Collapses R4-02 (CRITICAL).

4. **W7.4 community node registration** — register `kind='community'` nodes during Louvain; emit `member_of_community` edges; resolver accepts `community:` scheme. Collapses R4-N5.

5. **W7.5 doctor health threshold** — separate `orphaned_external_unresolved` (suppress) from `orphaned_inrepo` (count); add `malformed_uid_path` category for `../../` paths. Collapses R4-13, R4-25, R4-N9, R4-N10.

6. **W7.6 dep taxonomy** — new `kind='dependency'` for npm/pypi nodes; complete [project.optional-dependencies] walk. Collapses R4-N6 + finishes W6.7.

7. **W7.7 reindex prune mode** — `cos graph-reindex --prune-stale` deletes nodes whose file_path is missing; doctor `fix=True` extends to stale-paths category. Collapses R4-N7 + finishes W6.5.

8. **W7.8 stub-hub exclude list** — extend T1 fix: `__future__, typing, typing_extensions, __init__` excluded from path BFS intermediate hops. Collapses R4-12 + R4-24.

9. **W7.9 cos_graph_communities count consistency** — cap `count<=top_requested`; wire `min_size` filter. Collapses R4-03, R4-17.

10. **W7.10 cos_graph removed-stub cleanup** — delete the stub; remove from contracts indexer. Collapses R4-14, R4-N8.

## See also

- [audit-graph-os-round4-2026-05-27.md](../tasks/audits/audit-graph-os-round4-2026-05-27.md) — pointer doc
- [graph-os-round3-audit-findings-2026-05-26.md](graph-os-round3-audit-findings-2026-05-26.md) — R3 register (60 defects, mostly fixed)
- [graph-os-round3-fix-checklist-2026-05-26.md](graph-os-round3-fix-checklist-2026-05-26.md) — W6.1-W6.20
- [graph-explorer skill](../../src/core/skills/graph-explorer/SKILL.md) — coverage/truncation discipline
- [mcp-error-envelope.md](mcp-error-envelope.md) — envelope contract
