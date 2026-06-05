---
audit_id: doc-system-2026-06-05
task_id: doc-system
intent_detected_at: 2026-06-05T05:00:00Z
matched_exhaustive: [, , ]
matched_scope: [audit, verify]
predicates: [produce-audit-artifact, evidence-grounded-findings, no-silent-gaps]
status: in_progress
created: 2026-06-05
completed: null
---

# Audit: Documentation System — enterprise alignment, gaps, blind spots, failure scenarios

## Source Intent

Scope (paraphrased, no prompt leak): comprehensively review and improve the
documentation subsystem across every consumer project type and scenario —
per-stack scaffold variance, markdown discipline, token-friendliness, graph
indexing of all doc knowledge sources, RAG retrieval + cross-reference
discovery, headers/keywords/navigation, doc CLI/MCP tooling, enforcement so an
agent cannot freely corrupt docs (git versioning, hooks, audit), docs-as-SSOT
at code-edit time, scaffold scaling per scenario (mobile / web / services /
WordPress / IoT), git-init default. Find all gaps, blind spots, failure
scenarios, bottlenecks — enterprise-grade from day one, no overengineering.

**Method:** 7-dimension adversarial workflow (37 agents): each dimension
audited by an evidence-bound auditor, every critical/high finding independently
refuted against the producer before counting. 59 findings stand (1 critical · 17
high · 30 medium · 11 low); 2 refuted.

## Headline — the through-line defect: DOGFOOD GAP

The machinery is enterprise-grade **in the meta-repo** but a large fraction is
**dead or absent in every `cos init` consumer** — the organism the product
ships. Symptoms: TASK-122 (consumer graph blind to its own rules/skills),
TASK-119 (00-index regen never shipped), TASK-120 (scaffold domains lint-warn
day one), TASK-118 (no `.gitignore` → consumer commits the mutating DB),
TASK-121 (consumer ships no git/CI doc governance), TASK-123 (phantom ADR RAG
path), TASK-121 (staleness-check audits the meta-repo, not the consumer).
Secondary themes: SSOT enforcement is **advisory where it must be load-bearing**;
RAG/graph **coverage holes** (rules/skills/ADRs/adapters unindexed; cross-ref
depends on hand-linking); **missing stacks + thin scaffolds**; **tooling gaps**.

## Categories — Mandatory Coverage Table

Remediation tracked as epic `doc-system` (TASK-118 → TASK-139). "Open after" is
the count of findings whose task is not yet `complete`. Row flips to
`Verified=yes` / `Open=0` only when every mapped task closes.

| # | Dimension | Findings before | Fixed | Open after | Verified | Evidence (tasks) |
|---|---|---|---|---|---|---|
| 1 | D1 Taxonomy / header / nav contract | 8 | 0 | 8 | no | TASK-120,125,128,130,139 |
| 2 | D2 Per-stack + multi-stack scaffold / missing stacks | 10 | 0 | 10 | no | TASK-123,133,134,135,136 |
| 3 | D3 Graph indexing of docs + RAG + cross-ref | 8 | 0 | 8 | no | TASK-122,123,124,126,139 |
| 4 | D4 Doc CLI/MCP tooling sufficiency vs overengineering | 7 | 0 | 7 | no | TASK-131,132,139 |
| 5 | D5 Enforcement / governance (agent can't corrupt docs) | 11 | 0 | 11 | no | TASK-121,127,128,129,130 |
| 6 | D6 Scaffold scaling + consumer lifecycle (git-init) | 6 | 0 | 6 | no | TASK-118,121,132,138 |
| 7 | D7 Red-team failure scenarios + bottlenecks | 9 | 0 | 9 | no | TASK-119,121,130,137,138,139 |

## Finding Index (59 standing)

Severity is the post-verification corrected value. Each maps to its remediation task.

| ID | Sev | Kind | Title | Task |
|---|---|---|---|---|
| D3-F2 | crit | blind_spot | Graph walk skips symlinks → consumer rules/skills/commands absent from graph | TASK-122 |
| D1-F2 | high | gap | Scaffold docs use 7 non-enum domains → every cos init project lints to warnings | TASK-120 |
| D2-F1 | high | gap | dimensions:/skills: never generate or validate scaffold docs (automation gap) | TASK-133 |
| D2-F3 | high | gap | WordPress/PHP/Laravel, Flutter, Supabase, IoT have no stack template/scaffold | TASK-136 |
| D2-F4 | high | failure_scenario | Multi-stack docs share one tree, last-writer-wins collision (a11y proven) | TASK-133 |
| D2-F7 | high | bug | RAG misallocated: nextjs design/content unindexed; RN override points at absent dirs | TASK-123 |
| D2-F9 | high | gap | Payment / admin-panel / policy(privacy,terms) docs first-class in no stack | TASK-134 |
| D3-F3 | high | bug | rag-config points at phantom docs/architecture/adr/; 6 real ADRs unindexed | TASK-123 |
| D3-F6 | high | blind_spot | No implicit/semantic cross-ref — "a rule elsewhere that applies" undiscoverable | TASK-126 |
| D4-F3 | high | overengineering | cos_audit_log_* family + auto-capture hook is dead surface (no reader) | TASK-132 |
| D5-F1 | high | gap | docs-lint frontmatter contract advisory by default — never gates CI/commit | TASK-127 |
| D5-F2 | high | gap | Doc DELETE via rm writes no audit row + hard-deletes RAG chunks | TASK-129 |
| D5-F3 | high | blind_spot | doc-anchor gameable — no check the doc was read or even exists | TASK-128 |
| D5-F4 | high | gap | Freeform doc CREATE fully ungated — no header/task/anchor/audit required | TASK-127 |
| D5-F6 | high | gap | Consumer ships zero git-level doc governance + no CI from day one | TASK-121 |
| D5-F7 | high | gap | git pre-commit backstop runs no doc governance (anchor/template/header) | TASK-127 |
| D6-F1 | high | gap | cos init makes no first commit + ships no .gitignore → consumer commits the DB | TASK-118 |
| D7-F3 | high | failure_scenario | Consumers never receive regen_doc_index.py → 00-index regen silent no-op | TASK-119 |
| D1-F1 | low | gap | LAYER enum drift: linter rejects audit/playbooks layers real docs use | TASK-120 |
| D1-F3 | med | gap | 6 ADR files violate naming rule, zero frontmatter, no 00-index | TASK-125 |
| D1-F4 | med | gap | 34% of meta docs lack the mandatory > Nav: breadcrumb | TASK-128 |
| D1-F5 | low | gap | First generated 00-index omits the > Nav: line its own rules require | TASK-130 |
| D1-F6 | med | blind_spot | Linter + regen exclude docs/tasks/ → task-tree header drift never validated | TASK-128 |
| D1-F7 | low | bug | Long-form silently overrides short-form opening block on a mixed file | TASK-139 |
| D1-F8 | low | bug | regen_doc_index ordering non-deterministic + silent truncate at limit=500 | TASK-130 |
| D2-F2 | med | bug | go-fiber dimension points to security-review.md only django ships (dangling) | TASK-133 |
| D2-F5 | med | gap | Backend stacks asymmetric: django rich, fastapi/go/go-fiber get 2 docs each | TASK-135 |
| D2-F6 | med | gap | react-native (UI stack) has no design-tokens / screens-content spec | TASK-135 |
| D2-F8 | med | gap | python + meta stacks ship empty scaffold — no docs for library/CLI persona | TASK-135 |
| D2-F10 | low | overengineering | RN rag-config override is a near-full base duplicate that drifts | TASK-123 |
| D3-F1 | med | gap | src/core/rules + skills not in RAG — agent can't discover an applicable rule | TASK-122 |
| D3-F4 | med | gap | docs/adapters + docs/code-os-core-docs absent from rag-config sources | TASK-123 |
| D3-F5 | med | bug | Stale kind=doc_file on 6/10 rules + 116/122 skills (content-hash skip) | TASK-124 |
| D3-F7 | med | gap | Missing-frontmatter chunks lose Stage-1 metadata filtering; warn invisible | TASK-124 |
| D3-F8 | low | gap | Cross-file cites_heading edges dangle at conf 0.7 with no reconciliation | TASK-139 |
| D4-F1 | med | gap | No "create new doc from template" tooling — agent hand-copies frontmatter | TASK-131 |
| D4-F2 | med | gap | Audit trail stores only hashes — can't answer "show me prior doc versions" | TASK-131 |
| D4-F4 | med | gap | No "validate one doc" surface despite docs-lint supporting single-file arg | TASK-131 |
| D4-F5 | med | bug | doc-cheat-sheet decision tree points at template files that don't exist | TASK-132 |
| D4-F6 | low | gap | No doc-specific graph-neighbor op; generic context undiscoverable for docs | TASK-139 |
| D4-F7 | low | gap | cos_doc_* vs cos_audit_log_* families straddle one user need (doc lifecycle) | TASK-139 |
| D5-F5 | med | gap | enforce-doc-sync advisory-only — code contradicting SSOT doc ships freely | TASK-128 |
| D5-F8 | med | failure_scenario | 00-index regen non-atomic + fire-and-forget → concurrent corruption | TASK-130 |
| D5-F9 | med | bug | auto-prune path extraction heuristic — missed path leaves orphaned RAG chunks | TASK-129 |
| D5-F10 | med | blind_spot | capture-audit fire-and-forget — dropped capture silently loses audit row | TASK-129 |
| D5-F11 | med | gap | No enforcement an edited doc is committed — docs drift uncommitted forever | TASK-130 |
| D6-F2 | med | bug | Scaffolded docs/00-index.md ships broken link to retired ./tasks.md | TASK-121 |
| D6-F4 | med | gap | cos add-stack regenerates AGENTS.md but not 00-index/foundation-map | TASK-138 |
| D6-F5 | med | blind_spot | doc-cheat-sheet routes new docs into 5 dirs that don't exist at t=0 | TASK-138 |
| D6-F6 | med | bug | docs-staleness-check checks META-REPO internals, not the consumer's docs | TASK-121 |
| D6-F7 | low | bug | cheat-sheet references unscaffolded templates + changes.log archive drift | TASK-132 |
| D7-F1 | refuted(partial) | bug | rename read_error short-circuit skips delete_nodes_for_file prune (folded) | TASK-129 |
| D7-F2 | med | failure_scenario | 00-index regeneration non-atomic plain write — concurrent clobber | TASK-130 |
| D7-F4 | med | failure_scenario | Beginner runs doc-search FTS-only, no warning; rag extra never auto-installed | TASK-137 |
| D7-F5 | med | bug | list_doc_headers truncates BEFORE sorting — top-N is rglob order at scale | TASK-137 |
| D7-F6 | med | failure_scenario | cos_doc_headers_by full unbounded FS walk per call, no cache — O(total docs) | TASK-137 |
| D7-F7 | med | failure_scenario | Header/enum drift advisory + beginners get no git enforcement → unbounded | TASK-121 |
| D7-F9 | med | blind_spot | is_active era-correctness NULL-permissive — superseded spec served as current | TASK-138 |
| D7-F8 | low | bug | Domain-hint regex maps swimlane to domains absent from a project's frontmatter | TASK-139 |
| D7-F10 | low | bug | auto-reindex-shell-ops fallback STATE_DIR hardcodes .coding-os/claude | TASK-139 |

## Refuted (do NOT act on as stated)

- **D6-F3** — claim "docs-lint does not validate relative links" is FALSE.
  `make docs-lint` DOES validate relative links + anchors + dead read-next +
  symlink dirs via `audit_doc_links.py` and hard-gates. No work needed.
- **D7-F1** — "doc rename leaves stale graph nodes served as live" — the
  *serves-as-live* framing is refuted, BUT the sub-mechanism is real: a
  `read_error` short-circuit in `reindex_dispatch.py:189-193` skips
  `delete_nodes_for_file` prune. Folded into TASK-129 as a sub-fix, not a
  standalone finding.

## Strengths — already enterprise-grade (do NOT rebuild)

- `cos_doc_header` parser: tolerant of extra frontmatter keys, parses both
  long + short opening-block form, 8KB-bounded, symlink-safe (Rule 5).
- `docs-lint.sh` frontmatter regex + strict-mode seam (fail-open→fail-closed
  migration path); self-documents as SSOT mirror of docs-system.md.
- `auto-regen-doc-index.sh` + `regen_doc_index._splice_into_existing` —
  debounced, fail-open, preserves hand-authored content outside the fence.
- RAG Stage-1 metadata pre-filter (domain/layer/since/is_active) — the
  "metadata enforces reality" half of production RAG.
- `scaffold-boundary-contract` — per-stack CODE-lane isolation, hook-enforced,
  tested. Multi-stack CODE coexistence is solved (only DOCS lane is not).
- Idempotent `_overlay_scaffold` (never overwrites user edits); data-driven
  stack discovery (Rule 11); `audit_doc_links.py` hard link audit.

## Resume Marker

<!-- last_updated_row: 0 -->
<!-- next_unchecked_row: 1 -->
<!-- last_updated_at: 2026-06-05T05:00:00Z -->

## Notes

- This is a DESIGN audit → remediation epic, not a single-session grep sweep.
  "Open after" stays >0 until each mapped task reaches `complete`; the audit
  closes when all 22 tasks close. Per-task fixes carry their own verification
  (Verification Matrix) + commit.
- Decisions locked with user (2026-06-05): (1) execution order = create full
  backlog first, then execute batch-by-batch; (2) `cos init` ships `.gitignore`
  + an auto initial commit (TASK-118).
- Batch order = ROI: B1 consumer-dogfood (118-122) → B2 RAG correctness
  (123-126) → B3 enforcement (127-130) → B4 tooling (131-132) → B5 stacks
  (133-136) → B6 scale/polish (137-139).
- Overlap: TASK-119 (regen ship) intersects existing TASK-113 (another
  session's "fix auto-regen-doc-index dead path") — scope TASK-119 to the
  consumer-delivery gap, coordinate before editing the hook.
- **Relationship to the completed `doc-system-v2` epic** (the prior run): v2
  fixed the doc-KB IN THE META-REPO; this audit found the consumer-facing
  delta v2 left (the dogfood gap). Do NOT redo v2 work:
  - TASK-070 (done) indexed docs/governance + playbooks + workflow MIRRORS
    into RAG. Remaining (TASK-122/123): `src/core/rules/*.md` SSOT + skills
    are still not RAG sources, and the CONSUMER graph has 0 rule/skill nodes.
  - TASK-072 (done) fixed regen_doc_index's PYTHONPATH/ModuleNotFoundError in
    the meta-repo. Remaining (TASK-119): the script is not shipped to
    consumers (scaffold_manifest has 0 refs) — the hook no-ops in every
    organism. Audit ran on post-072 HEAD; finding is current.
  - TASK-074 (done) reconciled the docs-lint domain/layer enum. Remaining
    (TASK-120): scaffold docs still carry 7 domains absent from that enum.
- Full evidence (file:line per finding) lives in the workflow transcript
  wf_03691e0a-c46; this file is the durable index.
