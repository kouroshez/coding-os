# graph_os Audit — Implementation Checklist (self-executed)

Source: deep audit 2026-06-02 (7-dimension adversarially-verified workflow). This file IS the doc-anchor spec for the fixes below. Execute top-down, matrix-test + commit per group. No Scrumban task — direct trunk commits.

Legend: `[ ]` todo · `[x]` done · **FIX** safe now · **BOUNDED** right-sized slice · **DEFER** needs user OK (feature removal / large redesign).

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
- [ ] **FIX F4** — `detect_changes`: expose already-computed downstream consumers in output. (G3b)
- [ ] **BOUNDED F7** — `centrality`: add `metric=in_degree` (true chokepoint). (G3b)
- [ ] **BOUNDED F3** — `similar`: widen candidate pool to same-kind cross-file. (G3b)
- [ ] **F8** — phantom `accesses_field` in default-kind tuples: P3 cosmetic (never-matching kind in an IN clause is a no-op). Decide cut vs leave in G3b — low ROI, weigh test churn.
- Verify: ✅ `pytest src/core/graph_os/tests/` (712) + `server.py --test` (clean)

## G4 — Envelope trim (`thinking_os/tools/_shared.py`) ✅ 1266 passed + live repro
- [x] **FIX F1** — added `_trim_lists_balanced`: when ≥2 list buckets share the envelope, shrink the largest round-robin (never below 1) before the sequential ladder. Single-bucket tools unchanged. Live repro: `contracts(http,mcp)` now 32/64 + 33/78 (was 0/70). Markers + `result_truncated` consistent.
- Verify: ✅ `pytest src/core/thinking_os/tests/` (1266 passed) + repro + `server.py --test`.

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
