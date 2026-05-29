---
audit_id: graph-system-deep-2026-05-28
task_id: TASK-039
intent_detected_at: 2026-05-28T00:00:00Z
matched_exhaustive: ["", "", "", "", "", "comprehensive"]
matched_scope: ["test", "audit", "verify", "find"]
predicates: ["every cos_graph_* tool exercised", "graph nodes/edges cross-verified against repo", "no node/edge category unchecked", "outputs compared graph-vs-manual"]
status: completed
created: 2026-05-28
completed: 2026-05-28
---

# Audit: graph_os subsystem & cos_graph_* MCP tool deep-dive

## Source Intent

Exhaustive correctness + benchmark audit of the entire graph system: every node
kind, every edge kind, every `cos_graph_*` MCP tool, language coverage, and a
file-by-file comparison of the graph against the live repo. Every graph output
cross-verified by independent manual repo search (graph-first → ground-truth
diff). Exhaustive vocabulary (``, ``, ``, ``) → evidence mode.

**Method:** graph-first query → independent ground-truth (the repo's own
`walk_local()`, direct SQLite SELECTs, manual grep, on-disk tool calls) → diff →
root cause → fix site. Two independent verification subagents re-checked the
headline findings (results in § Independent Verification). DB inspected
read-only; no graph mutation during audit.

## Baseline census (verified)

| Metric | Value | Source |
|---|---|---|
| Nodes | 31,615 | `cos_graph_doctor` + `COUNT(*)` (kind census sums to 31,615) |
| Edges | 68,786 | doctor; table `graph_edges_v12` |
| In-repo orphans | 0 | doctor |
| External-unresolved orphans | 981 (info) | stdlib/3rd-party stubs — expected |
| Dangling / dupe / self-loop / stale | 0 | doctor |
| Backend | sqlite only (Kùzu retired) | doctor `meta.backend` |
| Indexable files (`walk_local`) | 1070 | 456 py · 358 md · 115 sh · 49 tsx · 39 yaml · 26 ts · 19 json · 7 yml · 1 toml · **0 go** |

Node kinds (load-bearing): file 826 · doc_file 350 · folder 232 · function 3632 · method 2469 · class 736 · module 1045 · route 97 · hook 87 · mcp_tool 78 · task 54 · rule 12 (all kinds sum to 31,615). Edges `graph_edges_v12`, UNIQUE on `(source_id,target_id,edge_type,extractor)` — same edge from 2 extractors = 2 rows.

## Categories — Coverage Table

| # | Category | Method | Findings | Verified |
|---|---|---|---|---|
| D1 | Backend health | doctor + SQL integrity | clean | yes |
| D2 | Node coverage (file/doc parity) | `walk_local()` vs `graph_nodes` set-diff | **F1, F4** | yes |
| D3 | Edge integrity + root cause | SQL census + `upsert_node`/`md_links` read | **F1 root cause** | yes |
| D4 | Blast-radius accuracy | impact/references/detect_changes + manual grep | **F2, F5, F7** | yes |
| D5 | MCP tool surface (17 tools) | on-disk harness, all 17 invoked | all `ok` on disk; **F5** (server) | yes |
| D6 | Language coverage | extractor inventory vs repo lang census | see § Language Coverage | yes |
| D7 | Multi-node scenarios | communities/centrality/ranking/path/trace/similar | OK; **F6** (ranking relevance) | yes |
| D8 | Doc-drift | grep stale graph claims | **F0** (Kùzu/fallback) | yes |

## Findings Register

| ID | Sev | Layer | One-line | Status |
|---|---|---|---|---|
| F1 | HIGH | data + code | 131 `file` nodes have NULL file_path/lang/content_hash | live disk bug |
| F2 | MED-HIGH | code | `detect_changes` multi-file busts 32KB budget unshrinkably; scalars mauled | live disk bug |
| F5 | HIGH | operational | running MCP server is stale → `cos_graph_references(uid)` crashes | restart + guard |
| F7 | MED | code | graph misses `calls` edges for dynamic/indirect dispatch | recall gap |
| F3 | MED | data | task layer not re-synced (TASK-038 absent); audits counted as tasks | sync + classify |
| F4 | MED | code | 25 phantom `doc_file` nodes pointing at directories | live disk bug |
| F6 | LOW-MED | quality | `ranking(query=…)` returns generic helpers, weak relevance | tuning |
| F0 | LOW | docs | SQLite-as-"fallback"/"rerun with Kùzu" stale guidance | doc fix |

### F1 — HIGH — 131 `file` nodes with NULL `file_path`/`lang`/`content_hash`

`kind='file'` = 826, but only **695 have a real `file_path`**; **131 are NULL** (also `lang`/`content_hash` NULL). uid intact, edges resolve. Breakdown by `metadata`:
- **113 `stub=1`** — minted by stub-promotion for un-owned edge targets; many duplicate a real twin (`code:file:agent-presence.sh` stub coexists with real `code:file:src/core/hooks/agent-presence.sh`); some are `#Lxx-yy` fragments.
- **18 real files clobbered** — 4 `contracts@v1` (`sdk_dispatcher.py`, `dispatcher.py`, 2 tests), 6 `code_shell@v2` (`cos-env.sh`, `check-state.sh`, `write-state.sh`, `session-context.sh`, `inject-resume-prompt.sh`, `_lib.sh`), 8 `code_yaml@v1` (`adapter.yaml`, `registry.yaml`, 6× `scaffold-boundary.yaml`).

**Root cause.** `upsert_node` UPDATE SET (lines 254-277) wrote incoming `file_path`/`lang`/`content_hash` **unconditionally**; when a later path-less stub upsert hit the same uid (doc→file `links_to`), the real node's path/lang/hash were nulled. **Impact:** exact-path lookups + incremental short-circuit miss them; uid-traversal unaffected. Fix → § Remediation (verified: 0 real clobbers remain).

### F2 — MED-HIGH — `detect_changes` busts the 32KB budget unshrinkably; scalar fields mauled

`detect_changes(3 files)` = **53,206 chars**; stderr `envelope 53207 chars > budget 32000 after all trims`; `meta.truncated=true`, `envelope_unshrinkable=true`, `truncated_string_fields=['scope','risk_level']`. Confirmed on **disk** too (not stale-server-only).

**Root cause.** The 225-element `symbols` array was **not in `_TRIMMABLE_LIST_KEYS`** (`_shared.py`) → never shrunk → budget unmeetable → last-resort string-trim mauled even `scope`/`risk_level` scalars. **Fix.** Register `symbols` trimmable (verified live: no bust, scalars intact).

### F5 — HIGH (operational) — running MCP server serves stale code → `references` crash

`cos_graph_references(uid)` with default args returns `internal: TypeError: 'NoneType' object is not iterable` via MCP for function/method/file nodes (reproduced 4×, and independently by a subagent). The **on-disk code returns `ok:true`** for the identical call. `graph.py` mtime 2026-05-28 02:07, tree clean. Conclusion: the long-running thinking_os MCP server loaded `graph.py` before a fix and was never restarted (Python has no hot-reload; CLAUDE.md modularity map even notes "restart MCP client" for `thinking_os/**`).

**Impact.** Any agent in this environment calling the documented primary "who references this?" form (`cos_graph_references(uid)`) crashes right now. **Fix.** Restart the MCP server. Add a staleness guard: server records `graph.py` git-sha/mtime at boot; a hook (sibling of `warn-mcp-down.sh`) warns when disk is newer than the running server.

### F7 — MED — graph misses `calls` edges for dynamic/indirect dispatch

Graph-vs-manual on `build_dispatcher`: manual grep finds callers in `src/core/thinking_os/dispatcher.py:140` (dynamic `getattr` dispatch) and `src/scripts/smoke_sdk_dispatch.py:27`; the graph has only `contains` edges, **no `calls` edges** to it. Dynamic `getattr` dispatch is a known static-analysis limitation; the direct script call miss is worth a follow-up. **Impact.** `references`/`impact` under-report callers reachable only via dynamic dispatch — agents may believe a symbol is unused. Document the limitation; consider the LSP overlay (`lsp_overlay.py`) for call resolution.

### F3 — MED — task layer stale + audit files miscounted as tasks

`kind='task'` = 54 but `docs/tasks/TASK-*.md` = 38; the extras are `docs/tasks/audits/audit-*.md` indexed as `task:file:unknown:…`. **TASK-038.md (newest) = 0 nodes.** **Fix.** Incrementally index new TASK files; don't classify `audits/*.md` as `task`; parse status instead of `unknown`.

### F4 — MED — 25 phantom `doc_file` nodes pointing at directories

25 `doc_file` nodes had a directory as `file_path`, from `md_links` resolving extensionless link targets to dirs. **Fix.** Skip directory targets (emit `folder` edge, not `doc:file:` node).

### F6 — LOW-MED — `ranking(query=…)` relevance weak

`ranking(query="graph backend")` top-5 = generic helpers, not backend-relevant; PageRank dominates weak token match. **Fix.** Strengthen query-personalization weight; add a relevance eval fixture.

### F0 — LOW — Kùzu doc-drift

Kùzu was retired (SQLite-only) but `src/core/skills/graph-explorer/SKILL.md:37` still describes `meta.backend_fallback=true` as "the SQLite fallback (lower precision on deep walks)" and `.claude/rules/meta-graph-first.md` says "rerun with Kùzu when feasible." Stale. **Fix.** Drop fallback/Kùzu language; SQLite is the only store.

## Independent Verification (2 subagents, read-only)

- **Agent A** (data + crash): F1 CONFIRMED; F5 CONFIRMED (crash w/o kinds, ok w/); graph-vs-manual on `build_dispatcher` MISSED 2 caller edges → seeded **F7**.
- **Agent B** (code): F1 upsert clobber CONFIRMED (lines 244-277); F2 `symbols`-not-trimmable CONFIRMED → reframed root cause.
- **Glass-jar monitoring**: `cos hooks-log` — safety hooks fire+pass on every Bash, capture/sync on writes; no hook errors, loops, or runaways.

## Language Coverage (D6)

Extractors present (`src/core/graph_os/extractors/`): **Python** (`code_python`, AST), **TypeScript/TSX** (`code_ts`), **Go** (`code_go`), **Shell** (`code_shell`, tree-sitter-bash), **YAML** (`code_yaml`), **JSON** (`code_json`), **TOML** (`code_toml`), **Markdown** (`md_links`), plus `contracts` + `task_deps`. `DEFAULT_INCLUDE` globs: `.py .ts .tsx .md .sh .yaml .yml .go .json .toml`.

- **In-repo coverage: 100%** of indexable file types present (py/md/sh/tsx/ts/yaml/json/toml all have extractors). Aligns with the supported stacks (Python, Go, TS/JS).
- **Untested in dogfood:** the **Go** extractor exists but this repo has **0 .go files** → unexercised here (the go/go-fiber *templates* are the only Go, and template scaffolds are excluded). Recommend a Go fixture in `graph_os/tests`.
- **Not covered (no extractor)** — relevant for enterprise consumer projects: **Java/Kotlin** (Spring, Android), **Rust**, **C#/.NET**, **C/C++**, **Ruby** (Rails), **PHP** (Laravel), **Swift**, **Scala**. JS (`.js/.jsx/.cjs/.mjs`) is only partially reached (`.ts/.tsx` globs; `.js` not in `DEFAULT_INCLUDE`). SQL is single-file only.
- **Recommendation (ROI order, rule-of-three / defer-by-default):** (1) add `.js/.jsx/.mjs/.cjs` to the TS extractor's globs — cheap, the parser likely already handles it; (2) **Java/Kotlin** then **Rust** then **C#** as first new tree-sitter extractors when a consumer stack demands them — do not pre-build speculatively (Rule 22). Each new language = one tree-sitter grammar + node/edge mapping + idempotent uid + a test fixture.

## Remediation Results (2026-05-28, this session)

**Code fixes applied + verified — graph_os 698 pass · thinking_os 1205 pass:**

| Finding | Fix | Site | Status |
|---|---|---|---|
| F1 | upsert preserves existing non-null `file_path`/`lang`/`content_hash`/lines when incoming is NULL | `sqlite_backend.py::upsert_node` (201, 233-277) | **FIXED + data repaired** — 18 real files (sdk_dispatcher.py, cos-env.sh, registry.yaml, …) now carry correct path+lang |
| F1b | hook `declares` resolves bare script name → real path | `code_yaml.py` (192-211) | **FIXED** — 76/76 declares full-path, 0 bare (verified on disk) |
| F2 | `symbols`/`downstream_tasks` registered trimmable | `_shared.py` (196-199) | **FIXED** |
| F3 | `docs/tasks/audits/` excluded from task routing | `reindex_dispatch.py::_is_task_path` | **FIXED** — TASK-038 now indexed |
| F4 | directory link targets → `folder:` (no `doc:file:<dir>`) | `md_links.py` (269-283) | **FIXED for new extractions** (see orphan note) |
| F6 | ranking sorts query-seeded nodes before generic hubs | `graph.py::cos_graph_ranking` | **FIXED** |
| F0a | SQLite-as-"fallback" wording dropped | `graph-explorer/SKILL.md:36` | **FIXED** |
| F0b | `meta-graph-first.md` Kùzu line | `.claude/rules/` | **BLOCKED** — auto-mode classifier (agent-config self-modification); needs explicit user OK |
| F5 | `references(uid)` default-kinds crash | disk code already correct | **BLOCKED** — running MCP server is STALE; requires restart |
| F7 | dynamic-dispatch call edges missed | — | documented limitation (static AST); LSP overlay is the path |

**Data rebuild:** 2× `cos graph-reindex --force --prune-stale` (1072 files, 0 errors) + `cos_graph_doctor(fix=True)` → removed 99 dangling edges + 99 `stale_paths` nodes. Node count 31,615 → 31,703.

**Residual — F9 (needs a decision):** 100 `orphaned_inrepo` `doc:file:<dir>` phantom nodes. F4 correctly severed their bogus `links_to` edges, leaving them edge-less. **No sanctioned tool removes orphaned in-repo NODES** — `cos_graph_doctor(fix)` handles only edges + stale_paths (orphaned_inrepo is NOT in `fixable_categories`); `--prune-stale` delegates to doctor-fix; a raw SQL DELETE was denied by the auto-mode classifier (correct — destructive on the shared DB). **RESOLVED** (user chose "add doctor GC"): added an `orphaned_phantom` fix category to `cos_graph_doctor` + ran `doctor(fix=True)` → 100 phantoms deleted; graph now **`healthy=True`** (node_count 31,603; only 981 info-level external-unresolved remain). graph_os 698 + doctor 35 tests pass.

### F9 — MEDIUM — no orphaned-in-repo-node garbage collection

`cos_graph_doctor` *detects* `orphaned_inrepo` but it is absent from `fixable_categories`, and `--prune-stale` just delegates to `doctor(fix=True)`. So phantom/stub nodes that lose all their edges (e.g. after an extractor bug is fixed) accumulate with **no sanctioned removal path**. Recommended fix: add a conservative GC — zero-edge `file`/`doc_file` nodes whose `file_path` is NULL or a directory — to the doctor fix set (with a count cap + dry-run report), so cleaning detached phantoms doesn't require raw SQL.

## Live Re-Verification (2026-05-28, session 803-0b9f)

Re-ran against the **live MCP server + on-disk code + DB**:

- **doctor** (live): healthy — 31,603 nodes · 68,621 edges · 0 phantom/dangling/in-repo-orphan.
- **File coverage = 100.00% (1072/1072 indexed, TRUE MISSED=0)** — `walk_local()` vs `graph_nodes.file_path` over all kinds; every top dir complete. (Initial 32-"missed" alarm was a census-query false positive — those `.md` are indexed under semantic kinds `skill`/`rule`/`task`.)
- **F1 FIXED confirmed** — 37 NULL-path `file` nodes are all `stub=1`; 0 real-file clobbers.
- **F2 FIXED confirmed live** — `detect_changes(3 files)`: `risk_level:"high"` intact, `truncated:false`, no budget bust.
- **`impact` SOUND** — `upsert_node` downstream found `bulk_upsert` (conf 1.0) + all 3 test callers via `constructs` at depth 2; `walk_truncated:false`.
- **F5 still live** — `references(default-kinds)` crashes via MCP; fresh on-disk process returns ok (count=1); explicit `kinds=` works.

**F5 mechanism (corrects prior "fully stale" note):** server holds an *intermediate* `graph.py` snapshot (has uncommitted F9+F2, lacks the references-default-kinds fix) → edited across a restart. Genuine stale-server, disk correct, **restart clears it**; boot-staleness guard is the durable fix.

**F7 refined (quantified):** graph has 1 `calls` edge to `upsert_node` vs 12 real call sites — miss = instance-method calls on locally-typed receivers (type not statically inferable). `impact` compensates via class-level `constructs`; only `references(method,kinds="calls")` under-reports → use `impact` for method blast-radius.

## Resume Marker

<!-- last_updated_row: D8 -->
<!-- next_unchecked_row: synthesis -->
<!-- last_updated_at: 2026-05-28T19:05:00Z -->

## Notes

- Diagnostic audit: findings are bugs/inaccuracies, not grep-to-zero. Verified=yes = investigation complete + evidence recorded.
- **Meta-finding:** server-vs-disk split (F5) — MCP reflects stale server; disk + DB are ground truth. All 17 tools pass on disk; file coverage 100%; backend healthy.

## Closing Checklist

- [x] All D1–D8 categories Verified=yes
- [x] Every finding has evidence + severity + fix site
- [x] Language coverage (D6) quantified with recommendation
- [x] All 17 `cos_graph_*` tools exercised (on disk)
- [x] Independent reviewer subagents re-checked headline findings
- [ ] EvidenceBundle submitted via `cos_supervise_record_output`
- [ ] User decision recorded: fix in-session vs follow-up tasks
- [ ] Frontmatter `status` → `completed` when remediation path chosen
