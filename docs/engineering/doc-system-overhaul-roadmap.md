<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-06-03 -->

# Doc-System Overhaul — Audit & Roadmap (2026-06)

> P: SSOT for the doc-system v2 program — verified gap register, reverse-engineered failure scenarios, and the MVP/v1/v2 task map that fixes the documentation engine before mass-producing stack templates on top of it.
> R: Picking up any `doc-system-v2` or `stack-coverage` epic task, or deciding whether a proposed doc-system change is in-scope.
> S: Day-to-day doc authoring — read [docs-system.md](../governance/docs-system.md) instead.
> N: [docs-system.md](../governance/docs-system.md), [docs-first-protocol.md](../governance/docs-first-protocol.md), [graph_os-queries.md](graph_os-queries.md), [polyglot-extractor-roadmap.md](../playbooks/polyglot-extractor-roadmap.md)

> Nav: [Parent Index](00-index.md)

## Why this program

The doc system has strong bones (header contract, anchor-to-doc tracing Rule 0/19, auto-index regen). The gaps are **specific and verified**, not systemic. Core architectural finding: the system has **two retrieval planes that don't talk** — graph_os (structure: `links_to`/`read_next`/`cites_heading`) and RAG (`cos_doc_search`: embeddings + metadata) — and the **highest-value content (always-active rules + playbooks) lives in neither search index**. It is reachable only by always-on loading or by an explicit markdown link.

## Session progress (2026-06-03)

Shipped + verified: **G1** (TASK-070, committed `a690f2c`) — governance + playbooks now indexed in RAG (`cos_doc_search`), closing F1. **TASK-072** — `regen_doc_index.py` `src/`-path fix; `make docs-index-regen` + the auto-regen hook work again under bare `python3`. **G3** (TASK-074) — `docs-lint` validates domain/layer against canonical enums (advisory + `COS_DOCS_LINT_STRICT=1` gate), enums are SSOT in docs-system.md + cheat-sheet, `playbooks→playbook` typo normalized.

Graph doc-indexing (verified via `graph-doctor` + direct SQL): docs ARE comprehensively indexed — 382 `doc_file` · 5365 `doc_heading` · 5725 `doc_frontmatter` · 47 `doc_external` · 20 `skill` · 13 `rule` nodes; `contains` / `links_to` / `read_next` / `cites_heading` edges. Cleaned ~60 zombie `doc_file` nodes (stale paths from past file moves + 1 malformed symlink + 1 phantom) via `graph-doctor --fix` → healthy. Zombie accumulation root cause: `auto-prune-deleted-files` only fires on `rm`/`git rm`/`mv` (failure F4) — recurrence-prevention is a follow-up under G5/F4.

Remaining: G4 · G5 (incl. F4 prune coverage) · G6 · G8 · G9 (clears the no-frontmatter backlog → flip docs-lint strict) · G11 · all stacks.

## Verified gap register

All evidence checked against source (not agent inference).

| # | Gap | Evidence (file:line) | Sev |
|---|---|---|---|
| G1 | Rules + playbooks excluded from semantic search | `.coding-os/rag-config.yaml:48-53` | HIGH |
| G2 | Graph plane ⊥ RAG plane — no cross-plane discovery | `tools/docs.py` vs `extractors/md_links.py` | HIGH |
| G3 | domain/layer enums declared but unenforced (`engineering` used 27× ≠ canon) | `src/core/scripts/docs-lint.sh:70` (`domain:[A-Z_]+ \| layer:[a-z]+`) | MED |
| G4 | No auto-tagging — every new doc needs hand-written frontmatter | no hook exists | MED |
| G5 | Reindex freshness race — fire-and-forget + 3–5s debounce | `auto-reindex-docs.sh` | MED |
| G6 | No prior-version recovery — audit stores content hash only; git not surfaced | `tools/audit.py` schema | MED |
| G7 | `cos init` runs `git init` but makes no baseline commit | `src/cli/_init_helpers.py:207` | LOW |
| G8 | No doc-authoring skill — agent writes docs blind to the contract | skill registry | LOW |
| G9 | Opening block is WARN not ERROR for content docs | `docs-lint.sh` | LOW |
| G10 | ~~Unsupported stacks get `_base` only~~ — RESOLVED: `src/templates/` now ships 27 stacks (laravel/wordpress/flutter incl.) | `src/templates/` (see dir) | DONE |
| G11 | Redundancy: dual opening-block syntax · 3× sections-by-layer · dual `.doc-anchor` path | `docs-system.md`, `doc-cheat-sheet.md` | LOW |

## Failure scenarios (reverse-engineered)

- **F1 — Silent rule miss (worst).** Agent edits code; a governance rule constrains the behavior but the code doc has no explicit link. `cos_doc_search` cannot surface it (G1). Change ships violating a live rule; no hook catches it (enforce-doc-sync only checks symbol drift). **Live today.**
- **F2 — Taxonomy rot at scale.** Invented domains/layers degrade the metadata pre-filter → `cos_doc_search(domain=…)` silently drops valid docs; graph communities blur. (G3)
- **F3 — Stale-read after edit.** Edit→immediate search returns the pre-edit chunk (G5).
- **F4 — Orphan graph nodes.** Rename outside `rm`/`git rm` leaves dead `doc:file` nodes (`auto-prune-deleted-files.sh` verb-gap).
- **F5 — Unknown-stack cliff.** Laravel/Flutter project gets base docs, zero stack playbooks/anatomy → agent invents conventions, drift. (G10) Note: TASK-069 adds PHP to the *graph extractor* but there is still **no PHP stack template**.

## Rejected (anti-overengineering filter)

`cos new-entity` generator · doc SemVer · blanket reverse code↔doc edges · `cos_doc_heading_search` · semantic multi-hop bias · chunk-dedup-by-hash · CODEOWNERS/review-before-write/`COS_DOC_MODE=readonly` (→ defer to `pr`-mode company seam) · building all stacks at once (→ demand-driven, one epic each).

## Roadmap → task map

**Engine — epic `doc-system-v2` (MVP+v1, implement first):**

| Task slice | Gaps | Swimlane | Verify row |
|---|---|---|---|
| RAG indexes governance+playbooks as searchable low-priority source-types | G1,G2 | thinking_os | thinking_os pytest |
| Enforce domain/layer enum + opening-block-as-error; reconcile canon with real values | G3,G9 | docs | docs-lint |
| Auto-frontmatter scaffold hook for new `docs/**/*.md` | G4 | core | verify-hooks |
| `cos doc-history` (git) + `cos audit-log` query CLI | G6 | cli | test_cli |
| Synchronous reindex path for edit-then-search | G5 | graph_os | graph_os pytest |
| `cos init` baseline initial commit | G7 | cli | test_cli |
| doc-authoring skill | G8 | docs | docs-lint / adapter render |
| Cut doc-system redundancy (one syntax · one sections-SSOT · unify anchor path) | G11 | docs | docs-lint + verify-hooks |

**Stacks — epic `stack-coverage` (v2, sequenced after engine; user requires full coverage):**

Graceful degradation + cheap add-stack path (G10) first, then one template epic each: Laravel/WordPress (leverages TASK-069 PHP extractor) · Flutter/Dart · Supabase · Terraform/IaC · Streaming/Linux-infra (nginx/ffmpeg/srs/LB) · IoT/embedded. Each: scaffold/docs + skills/anatomy + scaffold-boundary + stack.yaml dimensions + golden tests, per [template-authoring.md](../playbooks/template-authoring.md).

## Sequencing rationale

Engine before stacks: enforced taxonomy (G3), doc-authoring skill (G8), graceful degradation (G10), and auto-frontmatter (G4) make every subsequent stack template cheaper, contract-clean, and immediately discoverable. Building stacks first would bake today's drift into 7 new surfaces.
