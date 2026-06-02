# graph_os Audit — Implementation Checklist (self-executed)

Source: deep audit 2026-06-02 (7-dimension adversarially-verified workflow). This file IS the doc-anchor spec for the fixes below. Execute top-down, matrix-test + commit per group. No Scrumban task — direct trunk commits.

Legend: `[ ]` todo · `[x]` done · **FIX** safe now · **BOUNDED** right-sized slice · **DEFER** needs user OK (feature removal / large redesign).

## G1 — Coverage / ingest  (`ingest/base.py`, `tools/reindex_dispatch.py`, `hooks/auto-reindex-docs.sh`) ✅ 712 passed, hooks clean
- [x] **FIX F10** — index plain JS: added `*.js *.jsx *.mjs *.cjs` to `DEFAULT_INCLUDE` + `_EXT_MAP` (→ code_ts chain) + hook matcher.
- [x] **FIX F9** — added `json|toml` (and js variants) to `auto-reindex-docs.sh` matcher (was walk-vs-incremental drift).
- [x] **FIX F11** — extended `DEFAULT_EXCLUDE` with build dirs: `.next .nuxt .svelte-kit .turbo .gradle .terraform Pods vendor target` (high-confidence only; dropped generic `out`/`coverage`).
- [x] **FIX F14** — per-file size guard in `walk_local`: skip files > `COS_GRAPH_MAX_FILE_BYTES` (default 2MB), debug-log skip.
- Verify: ✅ `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` (712 passed/16 skip) + `make verify-hooks` (clean)

## G2 — Doc-linking  (`extractors/md_links.py`, `docs/playbooks/polyglot-extractor-roadmap.md`)
- [ ] **FIX F17** — `_resolve_link` repo-root fallback: when relative collapse → nonexistent path but a repo-rooted variant exists, use it (mirror `_resolve_read_target` bare-name anchoring). Kills 86 stale paths + reindex churn.
- [ ] **FIX F18** — skip image links (`![alt](x.png|svg|…)`) instead of routing to `code:file:`.
- [ ] **FIX docs** — un-stale roadmap: Go has ts rewrite (needs dep), Shell IS tree-sitter, JSON/TOML are first-class.
- Verify: `uv run --extra graph_os pytest src/core/graph_os/tests/test_md_links.py -q` + `make docs-lint`

## G3 — Tool output correctness  (`tools/graph.py`)
- [ ] **FIX F8** — drop phantom `accesses_field` from references/impact default-kind tuples (zero emitter). Leave the 6 unexercised-on-corpus types (real emitters).
- [ ] **FIX F5** — `resolve` confidence from rank, not flat 0.7 (FTS5 hits decay by position).
- [ ] **FIX F13** — `cos_graph_query` `_lexical_search`: try FTS5 `MATCH` before leading-wildcard `LIKE` (mirror resolve strategy-3). Future-proofs scale.
- [ ] **FIX F12** — Louvain: when input hits `LIMIT 50_000`, set `truncated:true` (coverage-honesty).
- [ ] **FIX F4** — `detect_changes`: expose the already-computed downstream consumers in output (currently walked then discarded).
- [ ] **BOUNDED F7** — `centrality`: add `metric=in_degree` (true chokepoint) ; keep `degree` but document fan-in+out conflation.
- [ ] **BOUNDED F3** — `similar`: widen candidate pool to same-kind cross-file (not just same-container + id-prefix sample).
- Verify: `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` + `python src/core/thinking_os/server.py --test`

## G4 — Envelope trim (`thinking_os/tools/_shared.py`)
- [ ] **FIX F1** — `_apply_token_budget`: proportional/round-robin trim across `_TRIMMABLE_LIST_KEYS` so no earlier bucket is zeroed while a later one keeps items (root cause of `contracts(http,mcp)`→`http_routes=[]`). Blast radius = every tool → careful + test_envelope.
- Verify: `uv run --extra rag pytest src/core/thinking_os/tests/test_envelope.py -q`

## G5 — Over-engineering cuts
- [ ] **FIX** — delete `enterprise.py::get_logger/_KVLogger/_fmt/_quote` (only genuinely-dead piece; RateLimiter/PrometheusSnapshot are load-bearing — KEEP).
- [ ] **FIX/gate F-LSP** — `lsp_client.py`+`lsp_overlay.py` (710 LOC) zero prod callers → remove module + tests + `types.py` provenance entry. (Reversible; archived TASK-041 was its wiring.)
- Verify: `uv run --extra graph_os pytest src/core/graph_os/tests/ -q`

## G6 — Packaging (`pyproject.toml`)
- [ ] **FIX** — add `tree_sitter_go` to `graph_os` extra so Go uses the shipped `code_go@v2` ts path instead of silent regex fallback.
- Verify: import check.

## DEFER — needs your OK (not over-engineering blindly)
- **F2** call-graph resolution lift (~28%→higher): self/instance-method type inference. Real design effort, own focused pass.
- **React/Next/RN component+hook modeling**: new feature (renders/hook/deps edges), not a patch.
- **CUT `viewer/` (graph-viz) + `groups/` CLI**: outward features — confirm before deleting.
- **Split `tools/graph.py` (4322 LOC)**: mechanical refactor, blast radius = server.py imports; own commit.
