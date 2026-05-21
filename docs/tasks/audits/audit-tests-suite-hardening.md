---
title: "Audit — tests/ suite hardening"
status: in_progress
created: 2026-05-21
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
| L1 | Suite not green — failing tests | TBD from baseline | CRITICAL | pending |
| L2 | Hang / timeout safety | pyproject, test_hooks_phase_m, hook test files | CRITICAL | pending |
| L3 | `@pytest.mark.slow` discipline missing | 10 heavy files | HIGH | pending |
| L4 | No shared `conftest.py` foundation | new tests/conftest.py | HIGH | pending |
| L5 | conftest migration — kill duplication | ~30 files | HIGH | pending |
| L6 | Runtime: function-scoped scaffold fixtures | test_template_scaffold, test_cli, test_doctor | HIGH | pending |
| L7 | Runtime: subprocess → in-process | test_intent_classifier, test_doctor, test_add_stack | MED | pending |
| L8 | Vacuous / hedged assertions | test_web_server, test_cli*, test_rag_pipeline, test_formula_composer, test_persona_integration, test_task_analyzer | HIGH | pending |
| L9 | Envelope under-assertion (Rule 13) | route test files | MED | pending |
| L10 | Dead / misnamed / misplaced tests + dead code | test_cli_*, test_hooks_*, test_phase_n_e2e, test_rag_pipeline, test_registry, test_doctor_suppress, test_adapters | MED | pending |
| L11 | `parametrize` under-used (copy-paste blocks) | test_task_analyzer, test_formula_composer, test_phase_n_behavioral, test_stack_registry, test_cli, test_cli_setup, test_adapters, test_codex_formula_commands | MED | pending |
| L12 | Hook test files split by commit-phase not concern | test_hooks_phase_{e,f,m}, test_hooks_new, test_hook_registry_integration | MED | pending |
| L13 | Redundant files + duplicated scenario tables | test_observability_smoke, test_phase_n_{behavioral,e2e} | MED | pending |
| L14 | Brittleness — source-grep, hardcoded lists, hand parsers, manual env mutation | test_brain_hardening, test_agent_presence_visuals, test_skill_registry, test_role_registry, test_no_hardcoded_anthropic, test_cli_update, test_multi_agent_dispatch, test_web_server, test_claude_dispatcher_options, test_stream_dedup, test_branding, test_golden_parity, test_phase_n_e2e | MED | pending |

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

Next: L1 (awaiting baseline run `/tmp/cos-baseline.log`).

## Evidence Log

| Item | Score (opt/speed/acc) | Verification | Commit |
|---|---|---|---|
| — | — | — | — |
