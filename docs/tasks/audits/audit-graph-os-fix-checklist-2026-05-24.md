# Fix Checklist — Graph OS Audit (TASK-029)

**Doc:** audit-graph-os-exhaustive-2026-05-24.md (root causes)
**Status:** in_progress

## Wave 1 — atomic line fixes (low risk)

- [ ] **F1 / #2 — resolve column-order swap** · graph.py:2787 · flip SELECT to `n.kind, n.label, n.uid, …` to match `_row_to_node`.
- [ ] **F2 / #6 — rename_plan edge types** · graph.py:1711 · extend `call_edge_types` with `constructs, has_param_type, inherits_from, dispatches`.
- [ ] **F3 / #19 — communities docstring drift** · server.py tool description for `cos_graph_communities` · say "named processes (Louvain)" not "communities/clusters".

## Wave 2 — semantic fixes

- [ ] **F4 / #5 — impact tier by edge_type** · graph.py:849 · `will_break` only when `edge_type in {calls, imports, constructs, accesses_field, has_param_type, inherits_from, dispatches}` AND conf>=0.5. Structural `contains` → `context` tier.
- [ ] **F5 / #14 — _safe_id collision-proof** · graph.py:2015 · use `f"{slug[:40]}_{sha1(uid)[:8]}"` so collisions impossible.
- [ ] **F6 / #10+#11 — centrality + ranking exclude noise** · graph.py:2128 + 2313 · default `WHERE n.uid NOT LIKE 'code:external:%'` and skip `code:module:<stdlib>` names.
- [ ] **F7 / #12 — ranking personalization token match** · graph.py:2386 · tokenize query, match any-token; OR run FTS5 to get seed uids.

## Wave 3 — coverage + diversity

- [ ] **F8 / #9 — communities member cap** · graph.py — cap `members` per process to ≤10 for MCP transport; full list optional via `expand_members` flag.
- [ ] **F9 / #7 — trace filter external** · graph.py:`cos_graph_trace` · skip `code:external:*` from `steps`, route to terminals.
- [ ] **F10 / #13 — entrypoints diversity** · graph.py:`cos_graph_entrypoints` · tie-break (score, file_path, start_line); diversify top-N across files.
- [ ] **F11 / #17 — context fuzzy-match wire FTS5** · graph.py:`_resolve_uid` · FTS5 last-resort fallback for unqualified labels.

## Wave 4 — extractor / doctor (more invasive)

- [ ] **F12 / #3 — self-loop drop in extractor** · graph_os/extractors/* · drop edge where source_uid==target_uid before emit.
- [ ] **F13 / #4 — stale-path resolution** · graph_os/extractors/md_links.py · resolve relative paths against doc dir before uid emit.
- [ ] **F14 / #16 — re-extract server.py** · run `cos graph-reindex --paths src/core/thinking_os/server.py --force` after F12 lands.

## Wave 5 — defer (needs spec or external)

- [ ] **F15 / #15 — path weighting** · DEFER · needs edge-weight table + spec before implementation.
- [ ] **F16 / #18 — file-uid vs module-uid asymmetry** · DEFER · doc-only; non-bug.

## Task lifecycle finding

- [ ] **F17 — TASK-029 YAML/DB drift** · board has `agent_session: ses-claude-pid50864` + `in_progress`, YAML frontmatter has `agent_session: null` + `started: null`. Investigate sync hook.

## Commit policy

One fix → one commit. Title ≤100 char, body ≤3 lines, no agent attribution.
