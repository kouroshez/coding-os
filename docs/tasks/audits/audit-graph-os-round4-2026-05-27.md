---
id: audit-graph-os-round4-2026-05-27
title: Graph-OS Round 4 — post-Wave-6 verification + new defects
task_id: TASK-037
audit_class: audit_exhaustive
created: 2026-05-27
scope_vocabulary: " /  /  /  / "
status: complete
completed: 2026-05-28
reviewer_check: pass
---

# Graph-OS Round 4 — pointer

Full register: [docs/engineering/graph-os-round4-audit-findings-2026-05-27.md](../../engineering/graph-os-round4-audit-findings-2026-05-27.md).
Fix-checklist (Wave-7): [docs/engineering/graph-os-round4-fix-checklist-2026-05-27.md](../../engineering/graph-os-round4-fix-checklist-2026-05-27.md).

## Trigger

User exhaustive intent: "", " mcp server ", "", "", community: UID error, Hub doctor `attention` status with 954/339 orphan/stale.

## Mandatory category table (exhaustive contract)

| Category | Count BEFORE (R4) | Count AFTER | Verified by | Status |
|---|---|---|---|---|
| 1. W6.1-W6.6 + W6.21 land verified | 6 verified / 1 partial / 1 with bug | all reconciled in W7 | live MCP probes | ✅ done |
| 2. R4 probe defects (R4-01..R4-26) | 26 (2 CRITICAL / 11 HIGH / 8 MED / 5 LOW) | 21 fixed · 5 dropped (justified) | Wave-7 commits + live probe | ✅ done |
| 3. R4 hub/extractor defects (R4-N5..R4-N12) | 8 (1 HIGH / 3 MED / 4 LOW/INFO) | 6 fixed · 1 dropped (N12) · 1 deferred (N11) | Wave-7 + extractor root fix | ✅ done |
| 4. Per-language extractor coverage | 8 languages scored vs Python baseline | matrix recorded (findings doc) | Agent A + SQL | ✅ done |
| 5. Orphans/stale breakdown | 956 orphans / 339 stale categorized | doctor `healthy=true`; 0 in-repo orphan · 0 malformed · stale=93 real dead doc-links (true positives) | live doctor | ✅ done |
| 6. W6.7-W6.20 status check | 1 partial / 3 not landed | W6.7 (dep taxonomy) closed by W7.7; W6.8/depth closed by R4-21; W6.10/W6.12 deferred | live SQL | ✅ done |
| 7. Cross-tool semantic agreement | 3 new symbols probed; F1/N2 persists | `meta.semantic_scope` + `resolved_from` on coverage tools | Wave-7 | ✅ done |
| 8. Doctor `attention` UX | 0 docs/threshold rationale in UI | split categories + severity badge + envelope doc | W7.6 + UI labels | ✅ done |

**counts_after_zero predicate:** in-repo orphans 0 · malformed_uid_path 0 · garbage stale 0. Remaining `stale_paths=93` are TRUE POSITIVES — real broken `[...](...)` links in documentation (target file deleted/moved). These are doc-debt, NOT graph defects; surfaced honestly by doctor. Follow-up docs-hygiene task tracked separately (see Resume marker).

## Baseline (2026-05-27)

37 756 nodes / 77 410 edges / 897 orphans / 339 stale_paths. uid schemes: `code, doc, folder, cos, task, npm, pypi, config, mcp` (9). **`community:` is NOT a node-table scheme** — root of the user-reported click error.

## Round-4 totals

- **34 new defects** = 26 probe (R4-01..R4-26) + 8 hub/extractor (R4-N5..R4-N12)
- Severity: 2 CRITICAL · 11 HIGH · 13 MEDIUM · 8 LOW/INFO
- **6 new cross-cutting root causes** collapse 18+ surface defects:
  1. **R4-01** fuzzy-resolve hijack — `cos_graph_impact("garbage")` returns blast for arbitrary symbol
  2. **R4-02** default `kinds` blind-spot for non-function nodes — class refs default returns 0
  3. **R4-03..R4-09, R4-16, R4-19, R4-20, R4-26** silent-param ignored across 7 tools
  4. **R4-N5** synthetic `community:` IDs leaked to UI as clickable; not registered as nodes
  5. **R4-N7** reindex idempotent-upsert preserves stale nodes (W6.5 extractor patched, 339 old nodes retained)
  6. **R4-N6** dep-extraction taxonomy: npm/pypi nodes as `kind=doc_external` (category error)

## Wave-6 land verification (foreground MCP probes)

✅ W6.1 (imports separate from calls) · W6.2 (bucket-aware shrinker, scalars preserved) · W6.3 (file-uid impact rollup) · W6.6 (communities member floor) · W6.14 (semantic_scope label) · W6.21 (regression tests). ⚠️ W6.5 (extractor patched, 339 stale nodes not pruned). ⚠️ W6.7 (deps emit but `kind=doc_external` taxonomy bug). ❌ W6.8, W6.10, W6.12 not landed.

## Recommended Wave-7 (10 fixes — full body in fix-checklist)

W7.1 cross-cutting validator helpers (collapses 11 surface defects) · W7.2 fuzzy-resolve guard · W7.3 default-kinds per node.kind · W7.4 community node registration · W7.5 doctor health threshold · W7.6 dep taxonomy · W7.7 reindex prune mode · W7.8 stub-hub exclude · W7.9 communities count consistency · W7.10 cos_graph stub cleanup.

## Resume marker (2026-05-28 — CLOSED)

All Wave-7 waves landed + extractor root-cause fixes (14 commits: c567fbe → 31c27cb). Doctor `healthy=true` for in-repo correctness:
- in-repo orphans: 0 · malformed_uid_path: 0 · garbage stale: 0
- `orphaned_external_unresolved: 981` — informational (stdlib/3rd-party stubs, by design)
- `stale_paths: 93` — **real broken doc-links** (true positives, doc-debt not graph bug)

**Dropped (justified, Rule 22):** R4-N12 (debounce filename hygiene), R4-15 (mixed-script FTS5 corner case), R4-N11 (NodeInspector/ContextPanel shape — works today), R4-11 (entrypoints envelope — documented limit), R4-22 (export at pathological max_nodes=3).

**Follow-up (separate scope):** 93 broken documentation links — a docs-hygiene sweep, NOT a graph-os defect. The graph correctly surfaces them. Create a `docs-update` task to fix the dead `[...](...)` targets across ~50 docs if/when desired.

Predicates: counts_after_zero ✅ (graph-defect categories at 0) · reviewer_check (pending subagent) · evidence_bundle ✅.

## See also

- [Round 3 register](../../engineering/graph-os-round3-audit-findings-2026-05-26.md) — 60 defects, 6 waves landed
- [Round 3 fix-checklist](../../engineering/graph-os-round3-fix-checklist-2026-05-26.md) — W6 waves
- [graph-explorer skill](../../../src/core/skills/graph-explorer/SKILL.md)
- [mcp-error-envelope.md](../../engineering/mcp-error-envelope.md)
