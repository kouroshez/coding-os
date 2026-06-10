<!-- domain:META | layer:checklist | ssot:false | updated:2026-06-02 -->
# graph_os Audit — Implementation Checklist (self-executed)

Source: deep audit 2026-06-02 (7-dimension adversarially-verified workflow). This file IS the doc-anchor spec for the fixes below. Execute top-down, matrix-test + commit per group. No Scrumban task — direct trunk commits.

Legend: `[ ]` todo · `[x]` done · `[~]` intentionally not changed · **FIX** safe now · **BOUNDED** right-sized slice · **DEFER** needs user OK (feature removal / large redesign).

## STATUS — all groups landed (7 commits on main)
`6d23326` G1 · `14fe17c` G2 · `aa8af3a` G3a · `675c840` G4 · `b535a0d` G6 · `bbda1a2` G5 · `341cbb8` G3b.
13 findings fixed + 1 documented-skip (F8). Each group: matrix-tested + live-smoked + committed with explicit paths (concurrent TASK-062 session ran throughout — no collisions).

### Operational follow-ups (NOT code — user/runtime action)
1. **Restart the MCP server** so the live `cos_graph_*` tools pick up the new code (`cos_graph_doctor` reports `server_stale: true`; tool behaviour changes — FTS5 query, balanced trim, in_degree, similar, detect_changes — load on restart).
2. **`cos graph-reindex --force`** to realize F17 (clears the 88 stale_paths via the new `_resolve_link`) + index the newly-included `.js/.jsx` + drop newly-excluded build dirs. Until then the on-disk fix is proven by unit repro but the live graph still shows the old nodes.

## G7 — Polyglot parity (TS/JS/React/Next/RN → Python-grade) ✅ 683 + 104 TS tests
Ground-truth showed `code_ts` was regex-gated behind a never-flipped `COS_EXTRACTOR_PREFERENCE` env var → only ~3/10 (no class/method/calls/type edges). Fix:
- [x] Built `_walk_ts_symbols` — tree-sitter AST walker (mirrors code_go@v2): class/interface/type-alias/function/arrow/method nodes; **calls sourced at the enclosing scope** (regex couldn't); inherits_from/implements/extends; is_decorated_by (class+method); has_param_type/returns_type; JSX component constructs.
- [x] Graduated it to the **default** path when the grammar parses (was env-gated). Regex stays as grammar-absent fallback. `.js/.jsx/.mjs/.cjs` + `.jsx`→tsx grammar.
- [x] Reconciled 2 regex-era tests (interface `extends`, class decorator) by adding those edges to the walker.
- [x] Framework routes verified via `contracts`: go-fiber (`app.Get/Post`) + Next.js (`export function GET/POST`) → `cos:route` + `handles_route`.
- Verify: ✅ 104 TS tests + 683 graph_os suite, zero regressions.
- **Live (post reindex --force + doctor --fix):** completeness scorecard — Python 12/12·TS/TSX/React **13/13**·JS/Go/Next/RN 10/10 on language-applicable constructs (Go has no decorators/class-inheritance; route files are functions-only — those N/A items aren't gaps). `.js` now indexed. `stale_paths 88→0`, `malformed_uid_path 19→0` (caught+fixed a self-introduced regression: chained-call uids), orphaned_inrepo 45→16. Only INFO `orphaned_external_unresolved` (stdlib stubs) remains.

### DEFER (still need your OK — unchanged)
F2 deep call-graph resolution (cross-file method receiver type-inference) · React hook-dependency graph (useState/useEffect dep edges — beyond Python's rubric) · CUT viewer/ + groups/ · split graph.py (4322 LOC).

## G1 — Coverage / ingest  (`ingest/base.py`, `tools/reindex_dispatch.py`, `hooks/auto-reindex-docs.sh`) ✅ 712 passed, hooks clean
- [x] **FIX F10** — index plain JS: added `*.js *.jsx *.mjs *.cjs` to `DEFAULT_INCLUDE` + `_EXT_MAP` (→ code_ts chain) + hook matcher.
- [x] **FIX F9** — added `json|toml` (and js variants) to `auto-reindex-docs.sh` matcher (was walk-vs-incremental drift).
- [x] **FIX F11** — extended `DEFAULT_EXCLUDE` with build dirs: `.next .nuxt .svelte-kit .turbo .gradle .terraform Pods vendor target` (high-confidence only; dropped generic `out`/`coverage`).
- [x] **FIX F14** — per-file size guard in `walk_local`: skip files > `COS_GRAPH_MAX_FILE_BYTES` (default 2MB), debug-log skip.
- Verify: ✅ `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` (712 passed/16 skip) + `make verify-hooks` (clean)

## G2 — Doc-linking  (`extractors/md_links.py`, `docs/playbooks/polyglot-extractor-roadmap.md`) ✅ 46 passed + live repro
- [x] **FIX F17** — `_resolve_link` repo-root fallback: collapse→nonexistent but repo-rooted variant exists → use it. Live: `../../docs/engineering/state-files.md` → `doc:file:docs/engineering/state-files.md` (was `src/docs/…`).
- [x] **FIX F18** — `_ASSET_SUFFIXES` skip: image/binary links return `''` (no `code:file:` mint). Live: `diagram.png` → `''`.
- [x] **FIX docs** — un-staled roadmap: Go (v2 ts shipped, dep missing), Shell (DONE tree-sitter), JSON/TOML (DONE first-class) + diagram lines.
- Verify: ✅ `pytest test_md_links.py` (46) + functional repro (F17/F18/good-link). Stale-path live cleanup deferred to final `graph-reindex --force`.

## G3 — Tool output correctness  (`tools/graph.py`, `communities.py`) — G3a ✅ 712 passed + self-test
- [x] **FIX F5** — `resolve` confidence rank-decayed (`0.9 − 0.05·idx`, floor 0.4); path_resolve stays 1.0.
- [x] **FIX F13** — `_lexical_search` tries FTS5 `MATCH` (indexed) before the leading-wildcard `LIKE`; LIKE preserved as fallback so recall holds.
- [x] **FIX F12** — `communities`: named `_SUBGRAPH_CAP`, `subgraph_input_truncated()` helper → `meta.input_truncated`, warns on cap-hit (was silent partial clustering).
### G3b ✅ 683 passed + live smoke
- [x] **FIX F4** — `detect_changes` now emits `downstream_consumers` (+`meta.downstream_consumer_count`); added to trimmable keys. Live: `_shared.py` → 23 consumers w/ provenance, risk=high (was symbols=contains-children only).
- [x] **FIX F7** — `centrality` gains `metric=in_degree`/`out_degree` (pure fan-in chokepoint). Live in_degree top: init_db(108)/database(83)/cos-env.sh(78) — not the fan-out UI pages the (in+out) `degree` surfaced.
- [x] **FIX F3** — `similar` same-label cross-file augmentation (deterministic). Live: `code_python::extract` now surfaces all **9** sibling `extract()` twins across extractor files (was 0).
- [~] **F8** — phantom `accesses_field` left as-is: P3 cosmetic no-op (a never-emitted kind in an IN-clause matches nothing). Removing it across 7 tuple sites risks default-kind test churn for zero functional gain → intentionally not changed (Rule 22: lowest-ROI, don't churn).
- Verify: ✅ `pytest src/core/graph_os/tests/` (683) + test_envelope (33) + `server.py --test` + live smoke F3/F4/F7.

## G4 — Envelope trim (`thinking_os/tools/_shared.py`) ✅ 1266 passed + live repro
- [x] **FIX F1** — added `_trim_lists_balanced`: when ≥2 list buckets share the envelope, shrink the largest round-robin (never below 1) before the sequential ladder. Single-bucket tools unchanged. Live repro: `contracts(http,mcp)` now 32/64 + 33/78 (was 0/70). Markers + `result_truncated` consistent.
- Verify: ✅ `pytest src/core/thinking_os/tests/` (1266 passed) + repro + `server.py --test`.

## G5 — Over-engineering cuts ✅ 683 passed (−33 dead tests), no dangling refs
- [x] **FIX** — deleted `enterprise.py::get_logger/_KVLogger/_fmt/_quote` + `__all__` entry + stale docstring + orphaned `import logging` + its 2 tests. RateLimiter/PrometheusSnapshot KEPT (load-bearing — power every Hub route).
- [x] **FIX F-LSP** — deleted `lsp_client.py`+`lsp_overlay.py` (710 LOC, zero prod callers) + `test_lsp_client.py`+`test_lsp_overlay.py` (30 tests) + `types.py` provenance entry + its test param. (Reversible via git; archived TASK-041 was its wiring.)
- Verify: ✅ `pytest src/core/graph_os/tests/` (683 passed) + import sanity + grep clean.

## G6 — Packaging (`pyproject.toml`) ✅ 716 passed (4 go tests un-skipped)
- [x] **FIX** — added `tree-sitter-go>=0.23.0,<0.26.0` to `graph_os` extra + mypy override. Go now uses `code_go@v2` tree-sitter path (returns_type/has_param_type/field_of_type/interface-embedding). Reconciled `test_code_go.py`: the regex-era `skips_inline_func_keyword` proxy → genuine `skips_func_keyword_in_string_literal` (tree-sitter correctly recovers a real func after junk; still skips func inside a string literal).
- Verify: ✅ import + `pytest src/core/graph_os/tests/` (716 passed, was 712 — 4 go tests now active).

## DEFER — needs your OK (not over-engineering blindly)
- **F2** call-graph resolution lift (~28%→higher): self/instance-method type inference. Real design effort, own focused pass.
- **React/Next/RN component+hook modeling**: new feature (renders/hook/deps edges), not a patch.
- **CUT `viewer/` (graph-viz) + `groups/` CLI**: outward features — confirm before deleting.
- **Split `tools/graph.py` (4322 LOC)**: mechanical refactor, blast radius = server.py imports; own commit.
