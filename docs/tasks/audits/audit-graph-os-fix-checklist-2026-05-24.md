# Fix Checklist — Graph OS Audit (TASK-029) + Followups (TASK-030)

**Doc:** audit-graph-os-exhaustive-2026-05-24.md (root causes)
**Status:** complete (all critical + medium landed; defer items captured as TASK-031 icebox)

## Wave 1 — atomic line fixes

- [x] **F1 / #2 — resolve column-order swap** · graph.py:2787 · flip SELECT to `n.kind, n.label, n.uid, …` to match `_row_to_node`.
- [x] **F2 / #6 — rename_plan edge types** · graph.py:1711 · extend `call_edge_types` with class-consumer kinds (DRY'd in F7b → `_BEHAVIOURAL_EDGE_TYPES`).
- [x] **F3 / #19 — communities docstring drift** · server.py tool description for `cos_graph_communities` · say "named processes (Louvain)" not "communities/clusters".

## Wave 2 — semantic fixes

- [x] **F4 / #5 — impact tier by edge_type** · graph.py:849 · `will_break` only on behavioural edges (DRY'd to module-level `_BEHAVIOURAL_EDGE_TYPES`).
- [x] **F5 / #14 — _safe_id collision-proof** · graph.py:2015 · `f"{slug[:40]}_{sha1(uid)[:8]}"` collision-safe.
- [x] **F6 / #10+#11 — centrality + ranking exclude noise** · default `include_external=False` drops `code:external:*` from input set.
- [x] **F7 / #12 — ranking personalization token match** · tokenize query, token-OR seed weight.
- [x] **F7b — uid-prefix-noise filter** · drop `code/doc/function/module/src/...` tokens before substring match (graph.py:2473+).

## Wave 3 — coverage + diversity

- [x] **F8 / #9 — communities member cap** · `max_members=10` default + `members_truncated` meta flag.
- [x] **F9 / #7 — trace filter external** · `code:external:*` → `external_targets` array, out of `steps`.
- [x] **F10 / #13 — entrypoints diversity** · round-robin across `file_path` within tied scores.
- [x] **F11 / #17 — context fuzzy-match wire FTS5** · `_resolve_uid` falls through to `_fts5_label_lookup`.

## Wave 4 — extractor / doctor

- [x] **F12 / #3 — self-loop drop at backend boundary** · `upsert_edge` returns `-1` on `source_uid==target_uid`.
- [x] **F13 / #4 — stale-path resolution** · md_links anchors `../` / `./` paths against source doc.
- [x] **F14 / #16 — re-extract server.py** · full reindex landed; `cos_graph` shim retained as fail-envelope tombstone.

## Wave 5 — task-lifecycle + DRY

- [x] **F17 / TASK-029 lifecycle** · `cos_task_create` stamps `started` + `agent_session` on `in_progress` only.
- [x] **F17b — convention narrowing** · removed testing/emergency from create-path stamp to align with `workflow.transition`.
- [x] **DRY — `_BEHAVIOURAL_EDGE_TYPES`** · module-level frozenset, single SSOT for impact + rename_plan.
- [x] **TASK-030 — role-* dual-mode** · 11 agent SSOT files: composer JSON + interactive prose + repo-aware auto-detect.

## Deferred (separate task)

- [ ] **F15 / #15 — path weighting** · DEFER · needs edge-weight spec.
- [ ] **F16 / #18 — file-uid vs module-uid asymmetry** · DEFER · doc-only.
- [ ] **F13b — embedded `..` regex** · DEFER · no real-world case (`docs/../foo.md` not in corpus).
- [ ] **security_auditor.md asymmetric interactive section** · DEFER · cosmetic.
- [ ] **TASK-031 (icebox)** — codex adapter parity + golden snapshot refresh + role-* dual-mode validation under Codex CLI. Pick up only when Codex adapter work resumes.

## Commit policy

One fix → one commit. Title ≤100 char, body ≤3 lines, no agent attribution.
