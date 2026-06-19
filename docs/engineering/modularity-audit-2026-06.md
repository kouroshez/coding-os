<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-06-19 -->
# Modularity / Auto-Sync Audit — June 2026

> P: The SSOT register for the 2026-06 modularity/auto-sync audit — every finding (F1–F16), its evidence, severity, verified status, and mapped task — plus the architecture verdict and the decisions locked with the owner.
> R: Before touching the modularity machinery (subsystems toggle, render pipeline, per-consumer rules, skill/hook disable, model routing), or before deleting any "dead" axis — confirm here why it was dead.
> S: Day-to-day feature work unrelated to module/skill/stack toggling — this audit is historical + governance.
> N: [mcp-error-envelope.md](mcp-error-envelope.md), [workflow-audit-2026-04-25.md](workflow-audit-2026-04-25.md), [../governance/critical-rules.md](../governance/critical-rules.md)

> Nav: [Engineering Index](./00-index.md) | [Docs Index](../00-index.md)

**Audited by:** Claude Code — 2026-06-16 (first pass) + 2026-06-17 (19-agent workflow, adversarially verified).
**Scope:** modularity / auto-sync only (markdown instruction sync, module/skill/stack/hook toggling, the render pipeline, model/adapter routing seam). NOT a full enterprise-readiness audit.
**Method:** dimension map → parallel per-dimension code reads → adversarial verification (refute-by-default) → synthesis → independent re-check of the top findings.
**Why this doc exists (R12):** the original R1–R15 register lived only in task labels + agent memory; R12 was lost because no audit doc was written. This file is the durable register so that never recurs.

## 1. Verdict

The modular / auto-sync vision is **half-built**, and the prior "vision ~built, not missing" verdict needed sharpening, not overturning:

- **Runtime-behavior half — genuinely built, mostly correct.** MCP tool capability-gating (`_gated_module` reads the SSOT live, fail-open), hook self-skip via `cos-env.sh` reading `disabled-hook-scripts`, the shared init/runtime apply-path (SI-1), and the module-aware `doctor` all work. It carried one silent bug (F1, now fixed).
- **Instruction-sync half — ~5/6 dead-on-arrival.** This is the literal thing the owner asked for ("toggle a module/skill/stack → add/remove the corresponding instructions/sections/files"). Today exactly **1 of 17** `AGENTS.md` fragments is module-gated; the two derived rule files ship **all-22-stacks** to every consumer via symlink; and there is **no working path to disable a core/stack skill**.
- **Architecture is SOUND but carries five declared-but-dead axes** that make it look more modular than it is. Per the Raptor principle (smaller+correct beats big+half-wired) these are DELETED, not extended.

**Most important blind spot:** the meta-repo dogfood guard means coding-os can **never** exercise its own AGENTS.md section-surgery, so "it's dogfooded" gives false confidence in exactly the audited feature. The first real test will be a real consumer — of which there are none. A consumer-in-CI harness is the missing proof.

## 2. Terminology (the owner's question, answered)

The umbrella is a data-driven **feature-flagged single-source-publishing pipeline**. Component terms:

| Concept | Term | Status in repo |
|---|---|---|
| Surgically edit one region of a hand-authored file | **Managed blocks / managed regions** (BEGIN/END markers) | one instance (`regen_doc_index.py` on `00-index.md`); not generalized |
| Emit different doc content per active feature | **Conditional content / profiling** (DITA), **single-source publishing** | the `AGENTS.md` fragment-assembly model (ungated) |
| Toggle a subsystem on/off gating its capabilities | **Feature flags / capability gating** | `_gated_module` (runtime, built) |
| Files regenerated, never hand-edited | **Derived / generated artifacts** ("auto-sync" = idempotent regen on source change) | `dimension-registry.md`, `skill-enforcement.md`, goldens |
| Strip tagged sections at init | **Conditional includes / tagged-content stripping** | `<!-- if-module:X -->` (TASK-360, the only working strip) |

## 3. Finding register (F1–F16) — adversarially verified

Severity: 🔴 high · 🟡 medium · 🟢 low. Status: open / **fixed** / deferred.

| ID | Sev | Finding | Evidence | Status / Task |
|---|---|---|---|---|
| F1 | 🔴 | Module gate keyed on `fn.__name__` not the registered MCP name → cos_search/cos_timeline/cos_details never gated when memory off; smoke test masked it | `_shared.py:862`, `server.py:457/467` (`name="cos_search"` vs `def thinking_os_search`) | **FIXED** c06e7163 (TASK-445) |
| F2 | 🔴 | `AGENTS.md` does not auto-sync to module toggles — only 1/6 modules drops prose | one `{% if modules.tasks %}` in `tool-routing.md.tmpl:2` | TASK-440 |
| F3 | 🔴 | Per-consumer rule files never rendered — every consumer gets all-22-stacks `dimension-registry.md` + `skill-enforcement.md` via symlink | `regen_rules.py` all-stacks world; `install-adapter.sh:125` verbatim symlink; goldens byte-identical | TASK-440 |
| F4 | 🔴 | No working path to disable a core/stack skill — CLI errors, Hub additive-only, `skill-overrides.json` has no writer | `skill_commands.py:423-428`; `project_overrides.py:51` (0 callers); false docstring | TASK-440 |
| F5 | 🔴 | Half-saved safety hook fails CLOSED on Claude (rc=2 = BLOCK every tool call); R14's dispatcher fix is Codex-only | `settings.template.json` direct hook calls; no `bash -n` at `install-adapter.sh` symlink | TASK-441 (re-scoped) |
| F6 | 🔴 | Model routing leaks bare tier names ('sonnet') as SDK ids; violates its own doc contract | `routing.py:24-29,97-106`; `cognition.py:1214` gates on `data_points>0`; `claude-sdk.md:188` | TASK-441 |
| F7 | 🔴 | Stack + module toggle round-trips are `@slow`/nightly-only — no fast PR guard on the primary surface | `test_cli.py:608` module-level slow mark; `test_remove_stack.py` all slow | **FIXED** 0bd8c6bd (TASK-447) — `test_modularity_toggle.py` in the PR job |
| F8 | 🔴 | Hook BLOCK failures never reach `log_events` — invisible to `cos_log_query` / auto-bug-filer | hooks log to jsonl only; only Python `_write_db` writes the table | **FIXED** aa5a7351 (TASK-447) — `cos_say_json.py` shared shell→DB writer |
| F9 | 🔴 | 32 non-safety hooks (of 83) belong to no module — untoggleable via the only working path | `registry.yaml`=83 vs `subsystems.yaml`=39; orphans incl enforce-skill/test-governor | TASK-440 |
| F10 | 🟡 | `design` module is a live no-op toggle | `subsystems.yaml:68-75` empty; live Enable/Disable in `ConfigPage.tsx` | TASK-440 |
| F11 | 🟡 | 4 golden fixtures captured but never asserted (drift-blind CI) | `capture_golden.py` 10 vs `test_golden_parity.py:33` 6 (claude_go-fiber/node-express/vue-nuxt, codex_go-fiber) | TASK-440 |
| F12 | 🟡 | Rule-11 enforcement split across 3 divergent sources + false 'mirrors' docstring | `test_no_hardcoded_stacks.py:29` frozen-6 vs `check_hardcoded_literals.py:46` discover_literals | **FIXED** cda16188 (TASK-441) — both share narrowed `discover_literals()`+`scan()`; skills + ambiguous ids dropped |
| F13 | 🟡 | Core `routing.py` hardcodes model tiers AND stack/skill ids — a Rule-11 self-breach the cli-scoped enforcer can't see | `routing.py:24-36` DEFAULT_MODELS/DEFAULT_SKILLS (incl stale 'bash-linux') | TASK-441 |
| F14 | 🟢 | Codex goldens store absolute temp paths → perpetually-dirty tree | `test_golden_parity.py:142` normalizes at compare-time only; 4 files dirty on capture | TASK-440 (cleanup) |
| F15 | 🟢 | Meta-repo AGENTS.md clobber guard in module toggle but NOT in add/remove-stack | `module_commands.py:56-60` guarded; `add_stack.py:269`/`remove_stack.py:389` not | TASK-440 (cleanup) |
| F16 | 🟡 | Routing ranks by success_rate only (→ always-Opus); `task_outcomes.model` NULL in 359/384 rows | `routing.py:108-142` no cost join; `record_outcome.py:113-128` returns None | TASK-441 (flag) + future routing task |

### Confirmed FIXED by prior work (credit, re-verified in code)
- **SI-1** (TASK-439): init + runtime share one `toggle_and_regen` apply-path. REAL.
- **Doctor module-awareness** + **meta-repo AGENTS.md clobber guard** (TASK-439). REAL.
- **CI gates** (TASK-438): golden-parity + render-smoke + skill-ref-integrity + logging_os/scheduled on every PR. REAL — but gates "render doesn't throw", NOT "toggle drops sections" (those are nightly — F7).
- **Hook self-skip is tested** at the execution layer (`test_project_overrides.py:68-93`).
- **TASK-360 doc-conditional strip** (`<!-- if-module:X -->`) IS wired at init.

## 4. R-series → F-series map

The 2026-06-16 register (R1–R15) was superseded by the verified F-series. Recovered mapping:

| R | Became | Task |
|---|---|---|
| R1, R5, R9, R15 | CI safety net (render-smoke, skill-ref-integrity, logging_os in CI) | TASK-438 (DONE) |
| R2, R3, R4 | SI-1 apply-path, module-aware doctor, meta-repo guard | TASK-439 (DONE) |
| R6, R7, R8, R13 | dead `requires:`, skill/hook-override no-writer, per-consumer rules, no-op design → F2/F3/F4/F10 | TASK-440 |
| R10, R11, R14 | tier-vs-id, Rule-11 unify, fail-open hook → F6/F12/F5 | TASK-441 |
| **R12** | **lost — never recorded in a doc.** This file IS the recovered R12 (the missing audit-SSOT-doc finding). | this doc |

## 5. Decisions locked with the owner (2026-06-17)

- **Granularity = HYBRID.** Module is the primary toggle unit (VSCode-extension model). SKILL is the one first-class per-item toggle (real token-cost ROI, zero safety risk). HOOKS stay module-bound — no per-hook writer; the 32 orphan non-safety hooks get assigned to modules instead (F9). Rationale: one mental model for plugin authors; per-hook toggling is a footgun + maintenance sink.
- **Per-consumer rules = RUNTIME-FILTER.** Keep `dimension-registry.md` / `skill-enforcement.md` on disk; filter to the consumer's installed stacks at Classify time (reuse `skill_primer.py` scoping). Do not break the live symlink with per-toggle file regen. Exclude the `meta` stack from non-meta consumers. Rationale: strictly smaller, preserves the propagation model, matches "runtime-gating beats regenerate-and-strip".
- **Dead machinery = DELETE all five, DOC-FIRST.** This doc records each before deletion: (1) `requires:` section-skip path; (2) `load_skill_overrides` + `skill-overrides.json` reader-with-no-writer + false docstring; (3) `Module.rules` / `Module.doc_tags` dead schema fields; (4) `routing_weights` recalc/drift self-licking loop; (5) `DispatchRequest.adapter` + `adapter_budget_usd` cross-adapter carriers. Rationale: a dead field that implies a feature is a liability for the plugin community (Rule 22); rebuild from the real SSOT if ever needed.

### 5.1 Implementation outcome (TASK-440, 2026-06-18) — two of the five were NOT dead

Adversarial re-verification during the delete pass found that "DELETE all five" was based on a stale read for **two** axes; deleting them would have broken live, contracted behaviour. What actually shipped:

| Axis | Decision | Shipped | Why |
|---|---|---|---|
| (1) `requires:` section-skip | delete | **DELETED** | No `stack.yaml`/`base.yaml` declared it; F2 used inline `{% if modules.X %}` gates instead. Removed field + renderer branch + schema property + its only test. |
| (2) `load_skill_overrides` + `skill-overrides.json` | delete | **DELETED** | Folded into the single `.coding-os.yaml::disabled_skills` store (F4). `install-adapter.sh` now reads it via `extract_disabled_skills.py`. |
| (3) `Module.rules` / `Module.doc_tags` | delete | **DELETED** | Zero readers (the `.rules` greps hit `RuleEntry`, a different type). Removed from dataclass + loader + every module in `subsystems.yaml`. |
| (4) `routing_weights` recalc/drift loop | delete | **KEPT** | NOT dead — live callers: `board_commands.py` (every 10 outcomes), `nightly.py`, `session-context.sh` (startup), 15+ tests. Deleting it also contradicts §6 ("keep feeding the learning loop"; populate `task_outcomes.model`). Re-scope to the routing task (F16) if its value is still doubted; do not delete blind. |
| (5) `DispatchRequest.adapter` + `adapter_budget_usd` | delete both | **HALF** — kept `.adapter`, deleted `.adapter_budget_usd` | `.adapter` has a live reader in `get_dispatcher` (the one-adapter-per-session mismatch warning, dispatcher-contract.md rule 6) and a test; only `adapter_budget_usd` was truly never read. `max_budget_usd` already carries the per-call ceiling. |

Lesson: a "dead axis" register is only as good as its last re-verification — confirm callers in code at delete time, never delete from the register alone. F9 was implemented as **total** hook ownership (all 83 registry hooks → exactly one module; new `cognition`+`observability` toggle modules; enforcement/meta/safety pinned to `kernel`), guarded by a new `test_every_registry_hook_has_exactly_one_module_owner` invariant.

The same lesson recurred in **F11**: independent post-merge verification (the matrix `test_template_scaffold.py` suite, which the delete pass had not run) found `claude_node-express` + `claude_vue-nuxt` were NOT orphans — `stack_lint.lint_all()` asserts a golden per stack via `test_factory_lint_passes_with_golden`, so deleting them turned 2 tests red. Both were restored; only `claude_go-fiber` + `codex_go-fiber` (asserted by no test — `go-fiber` has no `test_factory_lint_passes_with_golden`) stayed deleted. "Never asserted by `test_golden_parity`" ≠ "never asserted by any test" — the original F11 read checked only the parity SECTIONS list.

## 5.2 Pass-3 re-verification (2026-06-19) — RAPTOR-1/3 decision: KEEP routing_weights

A third adversarial pass re-checked `routing_weights`. Verified: `route_model` + `route_skill` rank from `task_outcomes` **directly** (`routing.py:95`/`:206`); `routing_weights` is only rebuilt (`recalculate_weights`) + staleness-checked (`routing_drift`), never **read** for a routing decision — a write-and-self-check loop (RAPTOR-1 confirmed). **Decision: KEEP, do NOT delete.** Its consumer is the cost-aware ranker that is multi-model **Phase 1** (designed + scheduled, deferred by the owner); deletion is premature + high-blast-radius (append-only migration v3/v26 cannot be removed, 15+ tests reference it). Wiring `route_model` to consult it now IS that Phase 1, so it stays out of this audit pass. Fixed instead: the `thinking_os-final-edition.md` store table that falsely listed `routing_weights` as written/consumed by `cos_route_skill/model` (corrected + marked not-yet-consumed), and a cross-reference between the two deliberately-duplicated recalc bodies (`routing.py` ⇄ the import-light `routing_evolution.py` hook helper — a Rule-8 decoupling, NOT a DRY accident; RAPTOR-3 left as a documented lockstep). B-4 (2026-06-19) fixed the upstream starvation so the loop now accrues real `model`+`complexity`.

## 6. Remaining roadmap

| Order | Task | What |
|---|---|---|
| 1 | TASK-446 | This doc (DONE on landing) |
| 2 | TASK-440 | BUILD: per-consumer rules (runtime-filter) + inline module gates (F2) + core-skill disable (F4) + hooks→modules (F9); DELETE the 5 dead axes |
| 3 | TASK-441 | tier→id resolver (R10), Rule-11 unify (F12), fail-open install/CI `bash -n` (R14), core self-breach (F13) |
| 4 | TASK-447 | fast PR-gated toggle round-trips (F7) + shell→log_events bridge (F8) |
| — | (new, recommended) | consumer-in-CI dogfood harness — the only real proof the toggle vision works end-to-end |

Self-driving multi-model routing (the owner's differentiator) is deferred: do NOT build cross-adapter dispatch now (Claude-only), but start populating `task_outcomes.model` so the learning loop has fuel (F16). The tier→id resolver (F6/F13) is its prerequisite.

## 7. Pass-3 backlog (2026-06-19) — adversarial re-verification + landed fixes

A third pass (43-agent workflow) independently re-verified the F1–F16 "closed" claims (4 of 8 spot-checked were only `real_but_partial`, one — F12 — carried a live consumer bug) and hunted blind spots the prior passes missed. All eleven items below landed:

| ID | Finding (audit ref) | Resolution |
|---|---|---|
| B-1 | Matrix suites (`test_cli`/`test_adapters`/`test_doctor`) are `@slow` → never on PR (F-TST-2) | new single-runner `test-matrix` PR job; in `ci-pass` |
| B-2 | `block-hardcoded-literals` resolved its checker to a nonexistent `.claude/scripts/` path → **silently inert** on every consumer (F12 live bug) | resolve via cos-env `_cos_helpers_dir`; loud-on-miss; set-e block-path fix |
| B-3 | Hub `/api/search/*` bypassed `_gated_module` → served disabled subsystems (F1 consumer hole) | per-project `module_state` gate on all 3 routes; `module_disabled`→403 |
| B-4 | `task_outcomes.model` NULL + complexity UNKNOWN on every MCP completion (F16 starvation) | shared `_state_search_dirs()` resolves `<state>/<agent>/.model` + panel gate; strip `ppid-` |
| B-5/B-6 | AGENTS.md commands tools whose module is off; graph/cognition/etc. ungated (F2 / RGC-B) | gate Core-Loop/Handoff memory+observability refs; graph/cognition/hub-extras have no always-on prose (correct-by-design) |
| B-7 | No out-of-tree plugin path — a community stack/adapter needed a fork (PLUG-1) | `$COS_USER_TEMPLATES_DIR` / `$COS_USER_ADAPTERS_DIR` overlay; no-shadow; adapters fail-soft |
| B-8 | `routing_weights` write-and-self-check loop with no decision consumer (RAPTOR-1/3) | KEEP (consumer = deferred ranker); fix store-table drift + cross-ref the duplicated recalc (§5.2) |
| B-9 | `logging_os` + `scheduled` had no `verify-suites.yaml` entry; test FAILs never reached `log_events` (F-TST-1/3) | add both suites; `record-verify-auto` `cos_say ERROR`s a FAIL into the sink |
| B-10 | `cos init --dry-run` not module-aware (INIT-4); manifest freshness nightly-only (INIT-1) | thread `--disable-module` into the preview; manifest freshness now in the test-modularity PR job |
| B-11 | Gating-mechanism map + fragment-structure contract + overlay undocumented (MD-3/MD-4) | this register + `template-authoring.md` sections |

Two more pre-existing CI-hidden REDs surfaced and were fixed in passing: `cos-env.sh` goldens stale since TASK-447's F8 (regenerated), and the manifest-freshness flake under concurrent tree writes (reliable on a static CI tree). **Still open** (owner-gated, not regressions): the consumer-in-CI dogfood harness (§6) and the multi-model cost-aware ranker (Phase 1).
