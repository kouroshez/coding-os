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

## 8. Pass-4 (2026-06-20) — EMPIRICAL consumer round-trip + 35-agent blind-spot hunt (TASK-470)

Passes 1–3 were all **code-read**, and each over-claimed "fully closed". Pass-4 ran the one thing they deferred: a **real `cos init` consumer** (`-t python -t go`, not in-memory render, not the meta-repo dogfood) was scaffolded and every optional module/skill/stack was toggled and **measured** — closing §1's "most important blind spot" (coding-os can never exercise its own section-surgery). A second 35-agent adversarial workflow (refute-by-default) then hunted seams the code-reads could not see.

### 8.1 Falsifiable per-module matrix (real consumer; baseline = 223-line `AGENTS.md`, 46 skills)

| module | `AGENTS.md` Δlines | skills removed | hooks gated | verdict |
|---|---|---|---|---|
| docs | 0 | 0 | 0 | DEP-BLOCKED (tasks→docs) — dependency-correct |
| **tasks** | **82** | 0 | 10 | ✅ full render-strip (`Scrumban`→0, `.bak`+regen) |
| graph | 0 | 0 | 8 | hooks gated; **no consumer prose** (B-5/6 confirmed); skill remains |
| memory | 6 | 0 | 8 | partial strip (Core-Loop refs) |
| cognition | 0 | 0 | 12 | hooks gated; no consumer prose (confirmed) |
| observability | 2 | 0 | 4 | partial strip |
| hub-extras | 0 | 0 | 2 | hooks gated; no prose |

Plus: `cos remove-stack go` = full cascade (skill unlink + path-rule removal + `AGENTS.md` −15 + backups); `cos skill disable` = symlink unlink + `disabled_skills` record; whole-matrix restore byte-identical; `log_events` live (hook BLOCKs queryable); registry staleness already covered by `cos doctor hub.project_paths_exist`; `--no-register` avoids debug pollution. **The toggle machinery itself is empirically SOLID** — Pass-4 did NOT reproduce the prior "over-claimed closed" pattern at this layer.

### 8.2 Verdict — REFUTED (qualified) at three adjacent seams

The module/skill/hook toggle core holds, but "the modularity machinery is solid" is refuted at: the **failure-rollback path** (P4-10), the **community-plugin overlay** (P4-3/6), and the **durable-logging + routing-attribution wiring** (P4-1/2/9). Plus one latent crash (P4-8) and one unenforced-invariant breach (P4-13).

### 8.3 New finding register (P4-1…P4-15) — adversarially confirmed, exact file:line in TASK-470 work-log

| ID | Sev | Finding | Status |
|---|---|---|---|
| **P4-8** | 🔴 | `cognition.py:1065` referenced undefined `field_map` → `NameError` on the schema-validation-failure path, masked as `fail("internal")` (hid the degraded-formula recovery the supervisor consumes) | **FIXED** `f962c383` |
| **P4-10** | 🔴 | `toggle_and_regen` rollback (`module_commands.py:89`) reverted only state, stranding `disabled-hook-scripts` on the failed-toggle state (inverted half-state); `doctor.py` checked one direction → certified it PASS | **FIXED** `8586bc98` (allowlist re-derived on rollback + bidirectional `extra = actual - expected` check) |
| **P4-1** | 🟡 | `cos_say_json.py:50` swallowed a `logging_os.sinks` import break bare → every hook BLOCK/WARN went durably silent with zero signal (drop-observability lives inside `_write_db`, never reached) | **FIXED** `bd0ee1a3` (COS_LOG_FILE breadcrumb, fail-open) |
| **P4-3/6** | 🔴 | Community-plugin overlay half-wired: `load_stack_registry`/`load_adapter_registry` accept `overlay_dirs` but **no** consumer command passes it; `overlay_adapter_dirs()` is dead code; B-7 closed clean with no tracking task; `template-authoring.md` oversells it as live | **FIXED** `6e5f2fa2` (TASK-471, PLUG-2) |
| **P4-13** | 🔴 | P8 invariant breached + unenforced: `src/core/web/routes/cognition.py` (NOT thinking_os/cognition.py) formerly held inline `ClaudeAgentOptions(...)` bypassing the importlib builder | **FIXED** `ab77c7f3` (TASK-472 — built only via the adapter importlib seam at `web/routes/cognition.py:598-605`; zero inline `ClaudeAgentOptions(`) |
| **P4-9** | 🟡 | `routing.py` learns `task_outcomes.model` = the **orchestrator** runtime model, never `formula_dispatches.model` (the true per-role model) → per-role recs structurally unfounded (the second-order defect B-4's population fix created) | **FIXED** `3c76fb9f` (TASK-473 — `COALESCE(fd.model, t.model) LEFT JOIN formula_dispatches`, `routing.py:100-102`) |
| **P4-2** | 🟡 | `COS_LOG_DB_MIN_LEVEL` not authoritative: console floor (`cos-env.sh:744`, `api.py:_emit`) gates before the DB floor → raising `COS_LOG_LEVEL` silently drops DB-eligible WARNs | **FIXED** `3c76fb9f` (TASK-473) |
| **P4-11** | 🟡 | Concurrent module toggles unlocked RMW + fixed temp filename (`subsystems.py:177`) → silent lost-update + torn write; contradicts git-workflow.md "concurrent sessions safe" | **FIXED** `1e14803d` (TASK-474 — flock + per-pid temp + dep-revalidation under lock) |
| **P4-14/15** | 🟡 | `enforce-skill.sh:84` unanchored `*core/*.py` substring demands `graph-explorer` with no meta-scope and no graph-module awareness → leaks the meta-repo-only block onto any consumer with a `core/`/`cli/` dir (recoverable, not a deadlock; #15 refutes #14's graph-module causal link — the hook is kernel-owned) | **FIXED** `1e14803d` (TASK-474 — `_in_meta_source_tree` + `_graph_module_disabled` guards) |
| **P4-12** | 🟢 | Corrupt `subsystems-state.json` fails open to all-enabled with only a debug log; next toggle **persists** the data loss; doctor reports PASS (fail-open *direction* is correct + tested — only the silent revert is the gap) | **FIXED** `1e14803d` (TASK-474 — `state_file_integrity` → doctor `modules.state_integrity` WARN) |

### 8.4 Re-confirmed known/deferred (not new)

- **P4-4/5** = the **B-7/PLUG-1 + B-11** partial closure (init/add-stack hard-abort on a community id; doc drift) — same area, sharpened into P4-3/6 above.
- **P4-7** = strategic-audit **latent-bug-(1)**: `route_model`'s empirical path emits a concrete (possibly retired) id to the SDK with no live-catalog validation (`_resolve_model_alias` exempts any `claude-*`). Fix when scheduled: one catalog guard inside the `claude-*` fast-return.

### 8.5 Owner decision pending — module↔skill coherence

`subsystems.yaml` has **zero `skills:` keys**, so disabling a module never touches a skill (disabling `graph` leaves the `graph-explorer` skill + its `AGENTS.md` mention). This is the direct consequence of the locked **Q1-HYBRID** decision (module/skill are independent toggle units) — NOT a regression — but the owner's recurring ask ("disable a module → its stuff incl. skills disappears") implies Q1 may warrant revisiting. Surfaced for decision; not unilaterally changed (Rule 22 / would contradict a locked decision).

## 9. Module-bundle completion — the five dimensions (2026-06-20)

Owner reframe: **a module IS a bundle of five artifact kinds — `{skills, hooks, MCP tools (or its own MCP), commands, rules/instructions}` — and disabling it must drop ALL of them "as if it never existed".** Coverage as of this entry:

| Dimension | In-context cost when module OFF but artifact present | Module-bound today? | Action |
|---|---|---|---|
| **Hooks** | hook fires on every matching tool call (wasted exec, possibly wrong nudge) | ✅ runtime allowlist + render-strip | DONE |
| **Rules / AGENTS.md prose** | tokens every session + commands the agent to use an absent tool | ✅ `{% if modules.X %}` render-strip (TASK-452 gated tool refs) | DONE |
| **Skills** | orphaned SKILL.md for an absent module; can instruct absent tools | ✅ data-driven `skills:` + targeted cascade (TASK-475) | DONE |
| **MCP tools** | **tool name in the agent's live tool list every session → hallucination + wrong-tool pick** | ❌ runtime-gate ONLY (still advertised, fails at call) | **TASK-476 + TASK-477** |
| **Commands** | slash-command file; NOT in context until the user types `/` → ~zero cost | ✅ data-driven `commands:` + ref-counted cascade (TASK-481) | DONE |

### 9.1 The MCP-tools gap (the real one)

The server registers **87 `cos_*` tools** (live count, verified 2026-06-20). `_gated_module` ([`tools/_shared.py`](../../src/core/thinking_os/tools/_shared.py)) only changes *call* behaviour — a disabled module's tool stays in `list_tools`, so the agent still sees it and hallucinates a call that then `fail('module_disabled')`s. That is "exists but broken", not "never existed". Measured tool→module ownership:

- gateable today: **graph 22 · tasks 21 · memory 9 · docs 3 = 55 / 87 (63 %)**; with cognition 15 + observability 7 (TASK-477) → **77 / 87 (89 %)**.
- `cognition` and `observability` modules carry `tools: []` — ~25 conceptually-theirs tools (compose/dispatch/supervise/route/situation/role · metric/log/trajectory/presence/digest) are stranded in the always-on kernel surface, so toggling those modules sheds nothing.

### 9.2 Decision (no over-engineering)

- **TASK-476 — surface removal (mechanism).** At stdio-server startup call `apply_module_tool_gating(mcp)` → `mcp.remove_tool(name)` for every disabled-module-owned tool (FastMCP supports it; per-project via `$COS_STATE_DIR`). Keep the per-call `safe_tool` gate as defense-in-depth (cached client list / mid-session toggle). Fail-open; `--test` keeps the full set. Per-project server ⇒ surface change applies **next session** automatically (new session = new server); the runtime gate covers the in-session window — so **no live `list_tools` reload / IPC is needed** (rejected as over-engineering).
- **TASK-477 (LANDED) — completed the tool→module map.** `cognition` ← dispatch_*/route_*/compose/supervise/role/situation/takeover/analyze/ambiguity/backtrack/discovery; `observability` ← metric_*/log_query/trajectory_*/presence; `memory` += retrieval_*/promote/digest. **Correction to the cautious framing above:** gating is *surface-only* (`remove_tool` from the agent's tool list) and never touches internal Python call paths — task-done outcome recording, hooks calling impl functions, etc. are all unaffected. So the real criterion is **semantic ownership + UX** (is the agent fine losing this tool when its module is off), not call-site safety. `cos_classify_prompt` (Record Gate) + `cos_health` (diagnostic) stay kernel by decision; `cos_traceability` + `cos_failure_pattern_query` stay kernel too (ambiguous ownership — not force-mapped, Rule 22). Result: disabling `cognition` sheds 15 tools, `observability` 7 (live-measured), on top of TASK-476's mechanism.
- **DEFER — "trim redundant tools even all-on" (curation-A).** The 20 task / 22 graph tools have overlap, but merge/delete is the **highest blast-radius, lowest-leverage** move. Surface-removal + map-completion sheds 61 %+ for free; revisit curation only with usage evidence, never by vibe.
- **DONE — commands dimension** now bound (TASK-481, pass-5): data-driven `commands:` axis + ref-counted cascade + `modules.command_drift` doctor check. **DEFER — module-owns-its-own-MCP** (the plugin/overlay path, TASK-471; Extension Manager P3, still DESIGN-stage).

Honest scope note: in Claude Code, MCP tool *schemas* are deferred (lazy via ToolSearch), so the primary win of removal is **less hallucination / cleaner tool list**, with a secondary, modest token saving — not a halving of context.

### 9.3 Skills dimension (TASK-477's sibling — LANDED, TASK-475)

The per-skill toggle machinery already existed (`skill_commands.set_project_skill` + idempotent `_relink_core_stack_skill`/`_relink_community_skill` + `cos skill enable/disable`). The only gap was *binding skills to modules*, so disabling a module did not shed its skills. Closed with the smallest data-driven change:

- **Data:** `subsystems.yaml::modules[].skills` (new optional list, sibling of `hooks:`/`tools:`); `Module.skills` in the loader. Conservative ownership — only **unambiguously meta-owned** skills: `graph` ← graph-explorer, graph-os-authoring · `memory` ← agent-memory · `tasks` ← task-driver. `clean-code`/`thinking_os`/`search` are always-on and **never** module-owned (asserted by `test_kernel_skills_never_module_owned`).
- **Collision trap avoided (api-contract-discipline):** the **`observability` skill** is a cross-cutting *app* skill (django/fastapi/go stacks list it for the consumer's own logging/metrics) — it is NOT the coding-os observability *module*. Mapping it would wrongly unlink it for those consumers, so `observability`/`docs`/`cognition`/`hub-extras` own no skills (same restraint as classify+health staying kernel for tools).
- **Mechanism:** a **targeted** cascade (`skill_commands.cascade_module_skills`) mirroring `remove_stack._unlink_stack_skills`, run from `module_commands.toggle_and_regen` after the state+allowlist+AGENTS.md regen. Disable → unlink owned skills **ref-counted** against other enabled owners; enable → relink owned skills **except** the user's `.coding-os.yaml::disabled_skills` (the override). `--keep-skills` skips the unlink; a TTY confirm previews the unlinks. Meta-repo guarded (`is_coding_os_source_tree`) exactly like the AGENTS.md regen, so a dogfood `cos module disable` never mutates the hand-maintained `.claude/skills/` links.
- **Deviation from the literal acceptance ("recorded in disabled_skills"):** the cascade writes **nothing** to the user's `disabled_skills` list. That list means *"the user explicitly opted this skill out"*; conflating it with *"the module is off"* would make re-enabling the module unable to tell the two apart (and would mislabel `cos skill project`). Instead the linked-state is **derived** (`linked ⟺ some owning module enabled ∧ skill ∉ user disabled_skills`), so re-enable relinks correctly and the override survives. `cos doctor` surfaces the residue via a `modules.skill_drift` WARN (disabled module, skill still linked).

## 10. Pass-5 (2026-06-20) — re-audit closure (TASK-480/481/482)

A third deep re-audit (8-dimension fan-out, adversarially verified against current code) confirmed the pass-1…4 machinery is **real, not half-wired** — the vast majority of findings were `correct-by-design` or `already-fixed`. Three real gaps closed:

- **TASK-480 (skill surface).** A module disabled **at init** now runs the same ref-counted `cascade_module_skills` as runtime `cos module disable` (D2-1); the rendered AGENTS.md `## Skills` (`INSTALLED_SKILLS`) is module-gated so a disabled module's skill no longer leaks into the list (D2-2 — `renderer._gate_installed_skills`, ref-counted, byte-identical all-on); `_relink_core_stack_skill`/`_relink_community_skill` are idempotent over a **dangling** symlink (D1-2); the gating smoke asserts the per-module skills count (D6-5).
- **TASK-481 (commands surface).** The **commands axis** is now bound (coverage table flips to DONE) — `subsystems.yaml::modules[].commands` + `module_commands.cascade_module_commands` (ref-counted, dangling-safe, meta-guarded) wired into `toggle_and_regen` and init step 5c, plus a `modules.command_drift` doctor WARN. `tasks` ← board/daily/retro/task · `memory` ← memory-search · `cognition` ← compose. `/role-*` (source-mapped from `thinking_os/agents/`) stay always-on (Rule 22).
- **TASK-482 (doc-sync).** This register's §8.3 was stale — 9 already-landed findings still showed "open → TASK-47X"; now marked FIXED `<sha>`, with the P4-13 file citation corrected. Tool count reconciled to the **live-measured 87** across this doc + `mcp-schema-traps.md`.

Still deliberately deferred (honest scope, not gaps): `module-owns-its-own-MCP` / community-MCP-tool seam (Extension Manager P3, DESIGN-stage) and all-on tool curation (revisit only with usage evidence, never by vibe).

## 11. Pass-6 (2026-06-20) — independent closure re-verification + owner-demanded open items (TASK-500)

Sixth pass — a 50-agent hostile-skeptic workflow (refute-by-default). Every Phase-A closure claim and Phase-B deep-dive finding was re-opened against current HEAD (`a222ab0d`) with real file:line evidence; the register's own claims were **not** trusted. Net: the over-claim pattern this audit chronically fought has **largely been broken at the mechanism layer** (35/36 closure claims fully verified, 1 partial), but **recurs at the docs and Hub-surface edges**. Two of the pass's own deep-dive findings were caught and refuted by the Phase-C verification layer — evidence the adversarial step works.

### 11.1 Closure re-verification result (Phase A)

| Cluster | Claims | Verified | Partial | Regressed/not_found |
|---|---|---|---|---|
| gate+logging (F1, F8, B-2, B-3, P4-1, P4-2) | 6 | 6 | 0 | 0 |
| agents-md+rules (F2, F3, F4, TASK-480) | 4 | 4 | 0 | 0 |
| hooks+goldens (F9, F10, F11, F5) | 4 | 3 | **1 (F5)** | 0 |
| routing (F6, F12, F13, F16/P4-9) | 4 | 4 | 0 | 0 |
| pass4-crashes+locks (P4-8,10,11,12,13,14/15) | 6 | 6 | 0 | 0 |
| cascades (TASK-475,481,476,477) | 4 | 4 | 0 | 0 |
| overlay (P4-3/6, B-7, TASK-479) | 3 | 3 | 0 | 0 |
| **Total** | **36** | **35** | **1** | **0** |

**True-closure rate ≈ 97%** — a sharp reversal of the prior "code-read pass over-claims closed" pattern. Caveats (noted, not counted as over-claims): F2's literal `TASK-452` task-id is unverifiable (no commit references it; the code state it describes is present + correct); F6 and F16 carry explicitly-deferred narrow edges (F6: a Hub-chat builder-failure can still leak a bare `sonnet` via `cognition.py:618-626` → `sdk_dispatcher.py:171`, which skips `_resolve_model_alias`; F16: routing ranking is still success-rate-only, no cost join).

### 11.2 The one PARTIAL — F5 (half-saved safety hook)

⚠️ **F5 — the install-time `bash -n` guard is real but does not eliminate the runtime fail-closed risk.** The cited fix is correct: [`install-adapter.sh:112`](../../src/core/scripts/install-adapter.sh) runs `bash -n` before symlinking each core hook (`:125` each dispatcher hook), skip+warn on a syntax-broken one. BUT: (1) Claude makes **direct** hook calls in [`settings.template.json:9`](../../src/adapters/claude/settings.template.json) (`block-secrets.sh`, no fail-open wrapper), so a hook that fails `bash -n` at runtime still exits `rc=2`=BLOCK on Claude — the R14 dispatcher fix is Codex-only by design; (2) `src/core/hooks/*.sh` are **live symlinks**, so a half-edited hook propagates instantly to already-linked consumers **without** re-running the installer — the install-time guard never re-fires; (3) no test exercises the `bash -n` skip path. Mitigated only by the convention-level atomic-edit protocol in `git-workflow.md`, not by code. **Status: open (low)** — accept as a documented residual or close via a regression test; do **not** add a runtime fail-open to Claude direct calls without owner sign-off (it changes safety-hook semantics).

### 11.3 Two deep-dive findings REFUTED by Phase-C (over-claims in the audit, not the code)

- **PB-1 ("tool-count 72 vs 87") — REFUTED; the count is genuinely 87.** Independent re-count: `server.py` registers **72** `cos_*` tools (via `name="cos_*"`) and [`cognition.py:1795`](../../src/core/thinking_os/tools/cognition.py) `register_all` registers a **second batch of 15** (the cognition family, incl. `cos_classify_prompt`) → **72 + 15 = 87**, matching §10's "live-measured 87". The orientation-phase "72" was an incomplete grep that missed the second `register_all` path — there is no discrepancy. (The deep-dive's own arithmetic was sloppy and was dropped; the structural fact — cognition registers via a second path — is real and now documented here.)
- **DOC-1 ("no docs↔module map") — REFUTED.** It manufactured a "sixth docs dimension" by misreading the §9 five-dimension reframe. A docs axis (`Module.doc_tags`) was **already** tried and deliberately deleted with rationale (§5 / §5.1, zero readers). Do **not** re-add a `docs:` schema axis. **However, three concrete docs *leaks* (DOC-3/4/5 below) survived verification as real** — the axis is dead-by-design, the specific leaks are not.

### 11.4 Confirmed-real finding register (Phase-B verified `real===true` only)

Severity: 🔴 high · 🟡 medium · 🟢 low.

| ID | Sev | Finding | Evidence (file:line) | Task |
|---|---|---|---|---|
| DOC-3 | 🟡 | Shipped governance docs reference disabled-module tools un-gated; `cos_doc_search` serves absent-tool guidance to a trimmed consumer | `scaffold/docs/governance/mcp-tool-inventory.md` header has `domain:DOCS` but **no `module:` tag**; `_apply_doc_conditions` wired at `main.py:871` but unused for graph/memory | **TASK-501** |
| DOC-5 | 🟡 | `cos remove-stack` orphans the stack's scaffolded docs — §8.1 "full cascade" over-claim recurs at the docs axis | `remove_stack.py:224` deletes only `rules_dir.glob("{stack}-*.md")`; `templates/go/scaffold/docs/{playbooks/go-service.md, engineering/go-rules.md}` never deleted | **TASK-502** |
| PB-3-tool | 🟡 | Default state advertises all 87 tools (gating is opt-out) — the owner's "too crowded → hallucination" IS the out-of-box experience | `tools/_shared.py` `_disabled_modules()` returns ∅ with no state file; `cos init` writes no disables; `subsystems.yaml` has no default-off field | owner-gated (§11.5) |
| HUB-PB1 | 🟡 | Hub Skills tab is additive-only — can add community skills but cannot disable a core/stack skill the backend already supports | `ConfigPage.tsx` button hardwired to `add` (`s.extra` false for core/stack); `set_project_skill` fully supports disable | **TASK-503** |
| HUB-PB2 | 🟡 | `modules.skill_drift`/`command_drift`/`state_integrity` never surface in the Hub — the toggle UI cannot show the drift its own cascade can produce | checks at `doctor.py:1095,1145,1191`; **zero hits** in `src/core/web/`; `DoctorPage` reads `/api/graph/doctor` (different producer) | **TASK-504** |
| DOC-4 | 🟢 | Runtime `cos module disable` never strips module-tagged docs — `_apply_doc_conditions` is init-only | only callers `main.py:701,871` (both init); `toggle_and_regen` never strips docs; no `modules.doc_drift` check | backlog (defer runtime doc-delete; add doctor WARN) |
| PB-4-hub | 🟢 | Hub discards the toggle's `regenerated` cascade notes (rollback/error feedback DOES reach the operator) | `ConfigPage.tsx` awaits `apiPatch` but discards body; CLI echoes each note `module_commands.py:302-304` | backlog |
| PB-3-skills | 🟢 | `ModuleRow` drops the `skills` count the producer emits — Hub under-reports module blast radius | producer `module_commands.py:266` `"skills": len(m.skills)`; consumer `ConfigPage.tsx` interface omits `skills` | backlog |
| PB-2-log | 🟢 | Startup log claims "14 tools" for cognition but `register_all` registers 15 (omits `cos_classify_prompt`) | `server.py:2226` "= 14 tools"; `cos_classify_prompt` registered `cognition.py:1814` | backlog (one-line) |
| PB-6-kernel | 🟢 | 4 always-on kernel tools (classify/health/traceability/failure_pattern) unmapped-by-omission, not declared kernel; no tool↔module totality test (hooks have one at `test_cli.py:1605`) | `_shared.py` `if module.get("kernel"): continue`; `subsystems.yaml:66` kernel `tools:[]` | backlog (documentation-as-data + invariant test) |
| PB-4-skillladder | 🟢 | ~9 of 22 graph tools (centrality, cycles, dead_code, diff, doctor, entrypoints, ranking, resolve, test_gap) carry no agent-facing guidance in any loaded skill/rule (corrected from the deep-dive's claimed 12) | `graph-explorer/SKILL.md` ladder vs `meta-graph-first.md` table; gating is all-or-nothing (`cos_graph_*`) | backlog (skill ladder, defer-curation) |
| F5 | 🟢 | Half-saved live-symlinked safety hook still BLOCKs at runtime on Claude (see §11.2) | as §11.2 | **TASK-505** covers the harness; F5 residual accepted |

### 11.5 Owner-gated decisions (RAPTOR / anti-overengineering applied)

| Item | Recommendation | Rationale |
|---|---|---|
| **Default tool surface** (PB-3-tool — the "too-crowded" complaint) | **Curated default behind `--full`:** `cos init` writes a starter `subsystems-state.json` disabling the heaviest COMPLICATED+-only module(s) (`cognition`, ~15 tools) unless `--full`. | Highest leverage for the owner's complaint, **no new code** (reuses existing gating). Owner-gated because it changes first-run behavior. Opt-in flip (all modules off by default) rejected — too aggressive, breaks existing consumers. |
| **Tool curation (merge/delete even all-on)** | **DEFER — keep §9.2.** | Highest blast-radius / lowest-leverage; no usage-telemetry source exists, so any merge now is by vibe (forbidden). Surface-removal + the curated default shed the crowding for free. |
| **Docs axis as a module dimension** | **Fix the 3 concrete leaks (DOC-3/4/5) only; no `docs:` schema axis.** | The axis was tried and deleted with cause; heavy reference docs genuinely do not ship. Real cost = 3 specific leaks, each fixable by reusing wired mechanisms. |
| **Q1-HYBRID (module→skill guidance coupling)** | **Keep LOCKED (§8.5); revisit owner-gated only.** | Skill cascade (TASK-475) already unlinks module-owned skills on disable; deeper guidance coupling has no proven need. Changing a locked decision unilaterally violates Rule 22. |
| **Consumer-in-CI harness** | **BUILD one thin single-module integration test (TASK-505).** | The durable guard against the unit-passes-but-end-to-end-half-wired pattern; would have auto-caught DOC-4/DOC-5. Keep single-module, not a matrix (Raptor: smaller+correct). |

**Pass-6 verdict:** the modularity machine is **genuinely built** (~97% true closure at the mechanism layer); the remaining work is **edge hygiene** — three docs leaks (TASK-501/502, DOC-4 backlog), Hub read-surface parity (TASK-503/504 + low backlog), a leaner default (owner-gated), and one durable end-to-end guard (TASK-505) — none of which are missing core machinery. Follow-up tasks: TASK-501..505 (filed, DoR-ready).

### 11.6 Implementation outcome (2026-06-21) — all five follow-ups landed

- **TASK-501** (`0094051e`) — shipped governance docs (`mcp-tool-inventory.md`, `agent-workflow.md`) wrap each tool family in `<!-- if-module:X -->` blocks; all-on output is byte-identical (verified via `_apply_doc_conditions`).
- **TASK-502** (`8fd49e26`) — `cos remove-stack` now deletes the stack's scaffolded docs too (`_remove_stack_docs`: manifest-driven, backup-before-delete, ref-counted, meta-guarded) + a fast unit test.
- **TASK-503** (`79eadfca`) — `config_skills` emits `provenance`+`disabled`; the Hub Skills tab renders Enable/Disable for core/stack skills (was additive-only).
- **TASK-504** (`44fe5ae3`) — `GET /api/settings/modules/drift` reuses the three `cos doctor` checks; ModulesTab shows a WARN banner.
- **TASK-505** (`55921670`) — fast in-process consumer-disable integration guard (skill+command symlink shed + tool gate; pins the DOC-4 runtime-doc-strip gap).
- **Discovered in passing — golden-parity is pre-existing RED on `main`:** the codex `role-*` commands + hooks shipped after the goldens were captured (`assert not [extra files]`, `test_golden_parity.py:151`); unrelated to the doc-gating change (confirmed). Filed **TASK-508** (recapture the 8 goldens).
- **Still owner-gated:** the curated default tool surface (PB-3-tool) — pending the owner's first-run-behaviour sign-off.

### 11.7 Profile system landed (2026-06-21, TASK-509)

The owner approved the curated default, shipped as a **profile system** (the enterprise progressive-disclosure pattern) rather than a one-branch `--full` switch:

- **Data:** `subsystems.yaml::profiles` — `core` (kernel+docs+tasks+graph), `standard` (+memory+observability, the `default_profile`), `full` (everything; byte-identical to a no-profile init). Each profile lists the modules it *disables*; `subsystems.resolve_profile()` validates unknown/kernel ids + dependency-safety.
- **CLI:** `cos init --profile <name>` merges the resolved disabled set into the existing `--disable-module` apply path (dependency-checked `set_module_enabled`). Omitted → the registry `default_profile`.
- **Coherence nudge:** a COMPLICATED+ `cos_classify_prompt` with `cognition` off returns a `nudge` field naming `cos module enable cognition` (Rule 15) — no silent `module_disabled` wall mid-plan.
- **Fixture safety:** `capture_golden.py` + `test_golden_parity._scaffold` pin `--profile full`, so a default-profile flip never silently shrinks the goldens; profile resolution is unit-tested separately.
- **Why a profile system over a hardcoded default:** least-surface-by-default + progressive disclosure + data-driven extensibility (community profiles) + auditability (the active profile is recorded state) — the VSCode-profile / systemd-target precedent. The Raptor move: a 3-way dial over the *existing* toggle machinery, not new machinery (anti-overengineering — earned by 3 real consumer cohorts, not speculation).
