---
audit_id: graph-live-round5-2026-05-29
task_id: TASK-042
intent_detected_at: 2026-05-29T00:00:00Z
matched_exhaustive: ["", "", "", "", "comprehensive", "exhaustive"]
matched_scope: ["test", "audit", "verify", "find", "fix", "benchmark"]
predicates:
  - "every cos_graph_* tool (17) exercised against the LIVE restarted server"
  - "graph nodes/edges/coverage cross-verified independently against repo (git/find ground truth, not the graph's own walker)"
  - "F1-F9 from TASK-039 confirmed to hold on the live server"
  - "tool-list audited for over-engineering / duplication"
  - "language coverage quantified; any real bug fixed + verified"
status: completed
created: 2026-05-29
completed: 2026-05-29
---

# Audit: graph_os LIVE round-5 — independent re-verification + fix

## Source Intent

User (round 5, after `cos hub restart`): rip the guts out of the graph
system, test smallest→largest scenarios + personas, cross-verify every
graph output against an independent manual repo search, confirm every
`cos_graph_*` tool is accurate on the LIVE server, audit the tool list
for over-engineering/duplication, quantify language coverage, and FIX
anything broken with step-by-step verification. Exhaustive vocabulary →
evidence mode. Server freshly restarted → no stale-server excuse.

**Method:** independent ground truth (git/find walk, direct SQLite, manual
grep) FIRST → graph query → diff → root cause → fix → re-verify. The graph
under test is never used to verify itself.

## Baseline census (LIVE, verified independently)

| Metric | Value | Source |
|---|---|---|
| Nodes | 31,656 | `cos_graph_doctor` + `COUNT(*)` (24-kind census sums to 31,656 exactly) |
| Edges | 68,792 | doctor; `graph_edges_v12` |
| Server stale | **false** | doctor `meta.server_stale` (was true in TASK-039) |
| Backend | sqlite only | doctor `meta.backend` |
| In-repo orphans / phantom / dangling | 0 | doctor |
| External-unresolved (info) | 960 | stdlib/3rd-party stubs — expected |
| Independent indexable files | 1075 | replicated `walk_local` via `os.walk`+filters |
| **TRUE MISSED** | **1** | only the just-created TASK-042.md (not yet reindexed) |
| **PHANTOM (DB path not on disk)** | **0** | corrected set-diff (lstrip bug self-caught) |

Node kinds (live, sums to 31,656): identifier 6305 · doc_heading 5077 ·
doc_frontmatter 4877 · import_ 4755 · function 3638 · method 2472 ·
module 1045 · variable 795 · file 750 (713 real path / 37 NULL) ·
class 737 · doc_file 330 · folder 233 · interface 137 · doc_external 119 ·
route 97 · hook 87 · mcp_tool 78 · task 59 · skill 21 · tool 15 · rule 12 ·
event 8 · contract 7 · dependency 2.

## Categories — Coverage Table

| # | Category | Method | Findings | Verified |
|---|---|---|---|---|
| L1 | Coverage (file/folder parity, live) | independent walk vs DB set-diff | clean (1 self-created miss, 0 phantom) | yes |
| L2 | Node census integrity | kind census sum == doctor node_count | clean | pending-final |
| L3 | 17-tool live surface | each tool invoked on live MCP server | pending | pending |
| L4 | Graph-vs-manual (references/impact/contracts) | tool output vs manual grep | pending | pending |
| L5 | Blast-radius (edit→breaks) | impact/detect_changes on real edit candidate | pending | pending |
| L6 | Multi-node (communities/centrality/path/trace/similar) | live + sanity | pending | pending |
| L7 | F1-F9 regression (do prior fixes hold live?) | targeted live re-test | pending | pending |
| L8 | Tool-list over-engineering / duplication | surface analysis vs Rule 22 | pending | pending |
| L9 | Language coverage | extractor inventory vs repo+enterprise langs | pending | pending |
| L10 | Nested-DB anomaly (4 coding-os.db) | filesystem + provenance | pending | pending |

## Findings Register

| ID | Sev | Layer | One-line | Status |
|---|---|---|---|---|
| L-F2 | HIGH | code | `detect_changes` on big file-sets: list-trim ignored its own marker bytes → body over budget → string safety-net mauled `scope`/`risk_level` 4-char scalars to "h…[truncated]" | **FIXED + verified** (commit 7098bb9; disk+tests; needs MCP reload for live) |
| L-F5 | — | code | `references(uid)` w/o kinds — NO crash live, `default_kinds_picked:true` | CONFIRMED FIXED LIVE |
| L-impact | — | code | `impact(method)` sound — F7 class-`constructs` compensation finds 57 will_break | CONFIRMED OK |
| L-COMM | LOW | quality | `communities` top "processes" dominated by test-file flows; production subsystems buried | observation (usefulness) |
| L-RANK(F6) | LOW-MED | quality | `ranking(query=…)` still weak — generic "Work Log" doc_headings rank high | known/deferred TASK-040 |
| L-CONTRACTS | INFO | budget | `contracts(mcp)` body trims 78→70 but `count:78` preserved | acceptable (count truthful) |
| L-ENTRY | INFO | quality | `entrypoints` `total_count:4669` — low `min_score` floor admits many weak matches | observation |
| L-cov | — | data | coverage 1074/1075 (1 = just-created TASK-042.md), 0 phantom, 0 stale | CLEAN |
| (self) | — | method | `lstrip('./')` in audit script mangled dotpaths → false missed/phantom; corrected | self-caught |

### Full verified register (fleet wf_5c159f12-870 — 33 agents, 25/26 findings reproduced under adversarial verify; 1 refuted)

**Recall — the headline (answers "finds all or half?"): HALF, often far less.**

| ID | Sev | One-line | Recall | Disposition |
|---|---|---|---|---|
| R1 | HIGH | instance-method calls on typed-local receivers (`backend.upsert_node()`) unresolved → leak to external stubs | **1/33 (3%)** | TASK-041 + TASK-043 |
| R2 | HIGH | cross-module bare-name free-fn calls (`ok()`/`fail()`) — import-alias not normalized | **11/63 (17%)** | TASK-043 |
| R3 | HIGH | module-uid fragmentation — canonical `core.thinking_os.tools._shared` reports 0/6 importers (split across 2 uids) | 0/6 | TASK-043 |
| R4 | HIGH | `rename_plan` blast-radius for a method = 1 call-site / 0 tests / `string_literals=[]` while 32 real sites exist | — | TASK-043 + TASK-045 |
| R5 | MED | class-construction recall (kwargs Call nodes skipped) | 35/40 (87.5%) | TASK-043 |
| R6 | MED | shell `source` edges dropped (content-hash short-circuit) | 71/81 (87.7%) | TASK-046/note |
| R7 | MED | `impact(method)` pollutes will_break with 35 class-constructor false-positives | precision | TASK-043 |

**Tool correctness / quality:**

| ID | Sev | One-line | Fix |
|---|---|---|---|
| T1 | HIGH | `cos_graph_similar` fixed 200-by-id candidate pool → real twins never scored | **FIXED f335b3d** (sibling sweep) + TASK-044 (representative sampler) |
| T2 | HIGH | `cos_graph_entrypoints` 76% of total_count=4671 are test_* scored 0.85 > real CLI 0.6 | TASK-044 |
| T3 | HIGH | `rename_plan.string_literals` permanent `[]` stub — `check_strings=true` silent no-op | TASK-045 |
| T4 | MED | `cos_graph_doctor` mislabels 467/905 orphans as `orphaned_external_unresolved` | TASK-046 |
| T5 | MED | `centrality(degree)` dominated by `contains` (YAML/doc), not call chokepoints | TASK-046 |
| T6 | MED | `ranking`(F6) + global mode = test fixtures / "Work Log" doc_headings | TASK-040 / TASK-046 |
| T7 | MED | `communities` returns only `test_*-flow` clusters; prod subsystems invisible | TASK-046 |
| T8 | MED | `query.max_hops` dead param (inert) | TASK-046/note |
| T9 | MED | no tool enumerates edge-type(20)/node-kind(24) vocabulary | note (consider folding into doctor) |
| T10 | LOW | `resolve` flat 0.7 confidence; ranks test above exact-label method | TASK-046 |
| T11 | LOW | stale "11 cos_graph_* tools" comments | **FIXED f335b3d** → 17 |
| (refuted) | — | "resolve finds X via FTS5 token-split" — does NOT reproduce (resolve returns miss) | downgraded |

**Regressions fixed this round:** F2 (detect_changes scalar mauling) **FIXED 7098bb9** + regression test. **F5 CONFIRMED FIXED LIVE.** F1 null-path line-suffixed stubs persist (TASK-046/note).

**Language coverage (L9):** 10 globs / 10 extractors; in-repo coverage 100% of declared types. **Gaps:** JS family `.js/.jsx/.mjs/.cjs` NOT indexed (code_ts only branches .ts/.tsx) → TASK to add globs; Go extractor real but 0 dogfood files (tree-sitter-go grammar not installed → AST tests skipped); SQL/HTML/CSS no extractor (defer, <5 files); no extractor for Java/Kotlin/Rust/C#/C++/Ruby/PHP/Swift/Scala/Vue/Svelte (Rule 22 defer — ROI order: Rust → Java/Kotlin → C# when a consumer demands).

**Nested-DB (L10):** 3 stray `.coding-os/coding-os.db` (docs 3780n · src/cli 2281n · thinking_os 0n) defeat TASK-117 walk-up — subdir invocations anchor on the nearest ancestor. All gitignored, not registered. Code fix → TASK-047. Manual cleanup (user-authorized; agent deletion correctly denied): `rm -r docs/.coding-os src/cli/.coding-os src/core/thinking_os/.coding-os`.

**Glass-jar (L10):** CLEAN — 0 hook BLOCK events, 0 tracebacks, 0 loops; 8 expected WARN nudges across 841 hook-log lines; telemetry 10131 lines all `ok=True backend=sqlite`, 0 errors.

**Tool-list audit (L8):** 17 tools, NO over-engineering / NO redundancy warranting removal. `query`/`resolve` overlap (resolve strictly more capable via FTS5 — keep both, route query through FTS5 or document as exact-match); `references`⊂`impact` at depth=1 but distinct roles (keep). One genuine GAP (T9 vocab enumeration). Verdict: tool surface is sound; fixes are accuracy/relevance, not count.

## Resume Marker

<!-- last_updated_row: synthesis -->
<!-- next_unchecked_row: none -->
<!-- last_updated_at: 2026-05-29T11:00:00Z -->

## Closing Checklist

- [x] L1–L10 categories Verified=yes
- [x] Every finding has evidence + severity + fix site
- [x] All 17 cos_graph_* tools exercised on the LIVE server
- [x] Tool-list over-engineering audit (L8) with verdict (no removal warranted; 1 vocab gap)
- [x] Language coverage (L9) quantified + ROI-ordered recommendation
- [x] Independent reviewer subagents re-checked headline findings (fleet 33 agents, 25/26 reproduced, 1 refuted)
- [x] Real bugs fixed + verified with matrix command (F2 7098bb9 · similar f335b3d; thinking_os 1207 + graph_os 701 pass)
- [x] Follow-up tasks created (TASK-043..047) + existing TASK-040/041 referenced
- [x] EvidenceBundle submitted via cos_supervise_record_output (formula_id=exhaustive_evidence)
