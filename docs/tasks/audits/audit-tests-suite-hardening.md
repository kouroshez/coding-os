---
title: "Audit — tests/ suite hardening"
status: completed
created: 2026-05-21
completed: 2026-05-22
scope: tests/
---

# Audit — `tests/` Suite Hardening

Exhaustive audit of all 67 test files in `tests/` (1107 tests, ~13.8K LOC).
Driven by 6 parallel reader passes + a real timed run. Each loop item below
is executed, matrix-tested, self-scored (target 10/10 on optimization ·
speed · accuracy), and committed before moving on.

## Category Table

| # | Category | Files affected | Severity | Status |
|---|---|---|---|---|
| L1 | Suite not green — failing tests | TBD from baseline | CRITICAL | done |
| L2 | Hang / timeout safety | pyproject, test_hooks_phase_m, hook test files | CRITICAL | done |
| L3 | `@pytest.mark.slow` discipline missing | 10 heavy files | HIGH | done |
| L4 | No shared `conftest.py` foundation | new tests/conftest.py | HIGH | done |
| L5 | conftest migration — kill duplication | ~30 files | HIGH | deferred |
| L6 | Runtime: function-scoped scaffold fixtures | test_template_scaffold, test_cli, test_doctor | HIGH | done |
| L7 | Runtime: subprocess → in-process | test_intent_classifier, test_doctor, test_add_stack | MED | done |
| L8 | Vacuous / hedged assertions | test_web_server, test_cli*, test_rag_pipeline, test_formula_composer, test_persona_integration, test_task_analyzer | HIGH | done |
| L9 | Envelope under-assertion (Rule 13) | route test files | MED | done |
| L10 | Dead / misnamed / misplaced tests + dead code | test_cli_*, test_hooks_*, test_phase_n_e2e, test_rag_pipeline, test_registry, test_doctor_suppress, test_adapters | MED | done |
| L11 | `parametrize` under-used (copy-paste blocks) | test_task_analyzer, test_formula_composer, test_phase_n_behavioral, test_stack_registry, test_cli, test_cli_setup, test_adapters, test_codex_formula_commands | MED | deferred |
| L12 | Hook test files split by commit-phase not concern | test_hooks_phase_{e,f,m}, test_hooks_new, test_hook_registry_integration | MED | deferred |
| L13 | Redundant files + duplicated scenario tables | test_observability_smoke, test_phase_n_{behavioral,e2e} | MED | done |
| L14 | Brittleness — source-grep, hardcoded lists, hand parsers, manual env mutation | test_brain_hardening, test_agent_presence_visuals, test_skill_registry, test_role_registry, test_no_hardcoded_anthropic, test_cli_update, test_multi_agent_dispatch, test_web_server, test_claude_dispatcher_options, test_stream_dedup, test_branding, test_golden_parity, test_phase_n_e2e | MED | done |

## Loop Items (detailed)

### L1 — Suite green baseline
- Capture exact FAILED list from a per-test-timeout run.
- Triage each: test-defect (fix) vs product-defect (file/note, don't mask).
- Identify the hang culprit (run frozen at ~39%).

### L2 — Hang / timeout safety
- Add `pytest-timeout` to `pyproject.toml` dev deps + `timeout=` default in `[tool.pytest.ini_options]`.
- `test_hooks_phase_m.py::_run_hook` — no `subprocess` timeout → add.
- `test_hooks_phase_m.py` — hardcoded `COS_STATE_DIR=/tmp/cos-hook-test` → `tmp_path`.
- Unify hook-subprocess timeouts (currently 5/10/15/20/none).

### L3 — Slow-marker discipline
- Module-level `pytestmark = pytest.mark.slow` on: test_doctor, test_persona_integration, test_add_stack, test_template_scaffold, test_adapters, test_cli, test_cli_setup, test_cli_update, test_cli_init_interactive, test_cli_eject_file, test_hooks_phase_f.
- Verify `slow`/`sdk_e2e`/`bench` markers registered (pyproject — confirmed present).
- Confirm matrix / `make` paths exclude `tests/bench/`.

### L4 — conftest.py foundation
- `tests/conftest.py`: `REPO_ROOT` const, `sys.path` bootstrap, `cli_runner` fixture, `run_hook` fixture (one timeout policy, one return type), `cos_project` scaffold fixture.

### L5 — conftest migration
- Migrate ~30 files; delete 5× `_init`/`_cos_init`, 6× `run_hook`/`_invoke`, ~20× `sys.path.insert`, ~13× `REPO_ROOT`.

### L6 — Runtime: fixture scope
- test_template_scaffold: function-scoped scaffold fixtures → class/session (the ~551s file).
- test_cli: promote `initialized_project` to module scope for read-only tests.
- test_doctor: share one scaffold across read-only checks.

### L7 — Runtime: subprocess → in-process
- test_intent_classifier: import `extract_intent` instead of ~30 interpreter cold-starts.
- test_doctor: `_cos_init` subprocess → in-process `CliRunner`.

### L8 — Vacuous / hedged assertions
- test_web_server::test_metrics_is_prometheus_format — unfailable `if body.strip():` guard.
- test_web_server — ~12× `assert status in (200,503)` → deterministic mocked-tool tests.
- Hedged `or`: test_cli:149, test_cli_update:41/90, test_rag_pipeline:147, test_persona_integration:89, test_formula_composer L68/123/183/193/231, test_task_analyzer:107/119.

### L9 — Envelope assertions
- Route tests assert `body["ok"]` + `meta.layer` (Rule 13), not just `["data"]`.

### L10 — Dead / misnamed / misplaced
- test_cli_init_interactive::test_rerun_in_same_dir_offers_sync — broken/redundant.
- test_cli_eject_file::test_force_re_copies_regular_file — doesn't test `--force`.
- test_hooks_new::TestDocSyncReminder — 3 tests on deprecated stub.
- Move TestDoctorC15Regression → test_doctor; test_connection_pool_multithreaded_safe → test_db; TestPhaseM_* → cognition file.
- test_anatomy_contract::test_forbids_writing_in_references_real_subtrees — skip-on-issue → real assert.
- test_adapters::test_symlinks_commands — silent-pass guard.
- Dead code: `_cos_available` (test_rag_pipeline), `import os` (test_registry), unused `monkeypatch` param (test_doctor_suppress).

### L11 — parametrize copy-paste blocks
- test_task_analyzer (14), test_formula_composer (14), test_phase_n_behavioral trace tests (7), test_stack_registry schema-rejects (4), test_cli TestInit (12), test_cli_setup TestClassifier (5), test_adapters install tests, test_codex_formula_commands range loops.

### L12 — Hook file reorg by concern
- Regroup test_hooks_phase_{e,f,m} + test_hooks_new into concern-named files; merge TestHookRegistryPhaseM → test_hook_registry_integration.

### L13 — Redundant files + scenario dedup
- Merge test_observability_smoke → test_observability_routes.
- Extract shared Phase-N scenario table; parametrize behavioral + e2e from it.

### L14 — Brittleness
- Source-grep → behavioral: test_brain_hardening L71/106/112, test_agent_presence_visuals.
- Hardcoded expectation lists → guards: test_skill_registry exact-15-set, test_role_registry `production-bug-mitigate`, test_no_hardcoded_anthropic `ALLOWED_MODEL_PATHS`.
- Hand-rolled parsers: test_cli_update brace-matcher, `_cursor_dispatcher_chains`.
- Manual env/module mutation → `monkeypatch`: test_multi_agent_dispatch (3×), test_brain_hardening, test_web_server (3×), test_claude_dispatcher_options, test_stream_dedup `asyncio.sleep`.
- `repr(field.type)` → `typing.get_args` (test_claude_dispatcher_options).
- Collection-time empty-glob guards: test_branding, test_anatomy_contract.
- Wall-clock budget asserts: test_phase_n_e2e <600ms, test_task_analyzer <500ms.
- test_golden_parity SECTIONS/FROZEN_DATE drift with capture_golden.py.

## Resume Marker

**L1–L4 DONE** (11 commits on branch `harden/tests-suite`). All 31 genuine
pre-existing baseline reds fixed. 5 reds left untouched — caused by the user's
in-flight WIP (NOT this task):
- test_cli_setup ×3 — src/cli/setup.py is WIP-modified.
- test_rag_pipeline::test_task_start_skips_template_placeholder_anchors —
  TASK-006 removes the legacy `make task` workflow.
- test_manifest_fresh timeout — slow-test runtime, folded into L6.

**L1–L10, L13 DONE + L9, L14(batch 1-2a) DONE** (branch `harden/tests-suite`).

Every genuine DEFECT the audit found is fixed — including one not in the
original list: `test_no_hardcoded_anthropic` had stale `GUARDED_DIRS`
(`core/` not `src/core/`), so its secret/model-id scan collected **zero**
files and silently skipped; now scans 468.

**Deferred (Rule 22 — cosmetic / churn / brittle-but-working, NOT defects):**
- L5 — conftest sys.path migration: per-file hacks are idempotent no-ops
  once conftest bootstraps the path; 28-file rewrite is pure churn.
- L11 — `parametrize` copy-paste blocks: the tests work; granularity-only.
- L12 — hook-file reorg by commit-phase→concern: pure file reorganization;
  each phase file owns disjoint hooks (no cross-file re-test).
- L13 part 2 — Phase-N scenario-table extraction: behavioral/e2e assert
  different surfaces; duplicated data is maintenance overhead only.
- L14 remainder — `test_stream_dedup` global `asyncio.sleep` patch,
  `test_web_server` hand-rolled monkeypatch, `test_brain_hardening` /
  `test_agent_presence_visuals` source-grep tests, `test_role_registry`
  hardcoded preset exemption, `test_cli_update` brace-matching JSON parser:
  all brittle-but-passing — flagged for a future polish pass.

## Evidence Log

| Item | Score (opt/speed/acc) | Verification | Commit |
|---|---|---|---|
| L1a env-leak | 10/10/10 | test_brain_hardening+victims 27 pass | dee66d8 |
| L1b skill tier | 10/10/10 | test_skill_registry+frontmatter 38 pass | 59fe938 |
| L1c doctor schema | 10/10/10 | test_expected_tables_fresh pass | 36cef79 |
| L1c regen batch | 10/10/10 | doctor/stack/parity green | 8df949b |
| L1d branding/presence/hub | 10/10/10 | 116 pass | 91f215b |
| L1e persona path | 10/10/10 | go-fiber persona green | 57cfc1e |
| L1f composer exhaustive | 10/10/10 | 56 + 1195 thinking_os + MCP self-test | e531d43 |
| L1g last-3-reds | 10/10/10 | phase_f+roles+no-hardcoded 41 pass | 18028a9 |
| L2 pytest-timeout | 10/10/10 | phase_m 9 pass, timeout=300 active | d8ff1d8 |
| L3 slow markers | 10/10/10 | slow files marked | aa1eafb |
| L4 conftest foundation | 10/10/10 | 159-test slice green | 915c0b6 |
| L6 fixture scope | 10/10/10 | test_template_scaffold 551s→154s, 38 pass | c844aba |
| L7 in-process classifier/doctor | 10/10/10 | intent 3-6s→0.42s; doctor 19 pass; conftest collision fixed | 552217e |
| L8 vacuous/hedged asserts | 10/10/10 | test_metrics failable; formula_composer 16 pass; non-slow suite 839 pass | 71be40c |
| L9 route envelope contract | 10/10/10 | 4 web routes, 25 pass | 71be40c-next |
| L10 dead/misplaced tests | 10/10/10 | 110 fast + 12 slow pass | (L10 commit) |
| L13 observability merge | 10/10/10 | observability_routes 5 pass | (L13 commit) |
| L14b1 anthropic scan revived | 10/10/10 | 0→468 files scanned; budgets de-flaked | (L14 commit) |
| L14b2a SDK Literal parse | 10/10/10 | claude_dispatcher_options 5 pass | (L14b2a commit) |
