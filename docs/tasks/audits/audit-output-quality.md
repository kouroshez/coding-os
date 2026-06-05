<!-- domain:INFRA | layer:audit | ssot:true | updated:2026-06-05 -->
# Audit — Script & Command Output Quality

> Nav: parent task [TASK-100](../TASK-100-script-command-output-quality-remediation-runtime-params-pro.md) · rubric [script-checklist](../../../src/core/skills/shell-scripting/assets/script-checklist.md) · reference impl [verify_since_edit.py](../../../src/cli/verify_since_edit.py)

status: in_progress
phase: discovery-complete · remediation-pending

## Scope & rubric

Audit every **make target · cos CLI command · standalone script · hook · test** against the
7 script-output non-negotiables (coding-os `shell-scripting` skill):

1. **runtime_params** — inputs via flags/args/env w/ defaults; no hardcoded paths/hosts/constants
2. **error_handling** — fail-closed (`set -euo pipefail` / non-zero exit + try-except); no `|| true` on real failures
3. **idempotency** — re-run safe; clobber needs `--force`
4. **progress** — slow work (network/subprocess/many-file loops/>1s) narrates to **stderr**
5. **result_precision** — stdout = parseable RESULT; stderr = NARRATION; never mixed; clear exit codes
6. **algo_efficiency** — no O(n²) where O(n) works; no per-iteration subprocess/connection spawn
7. **header** — top-of-file PURPOSE/INPUT/OUTPUT/DEPENDENCIES/NOTES contract

## Method

9 parallel auditor agents (Workflow `output-quality-audit`, run `wf_5c81fa05-5f6`, 1.08M tok, 206s) ran the
mechanical linter (`lint_script.sh`, shellcheck 0.11) then read each file to judge the criteria the linter cannot.

## Ground-truth mechanical counts (grep, pre-fix)

| Probe | Count | Command |
|---|---|---|
| Makefile targets | 86 | `grep -cE '^[a-z0-9_.-]+:' Makefile` |
| cos CLI modules | 34 | `ls src/cli/*.py` |
| standalone py scripts | 28 | `ls src/scripts/*.py src/core/scripts/*.py` |
| standalone sh scripts | 13 | `ls src/scripts/*.sh src/core/scripts/*.sh` |
| event hooks | 90 | `ls src/core/hooks/*.sh` |
| test files | 253 | `find tests src -name 'test_*.py'` |
| hooks missing `set -euo pipefail` | **13 / 90** | per-file grep |
| standalone .sh missing header | **11 / 13** | per-file head grep |
| standalone .py missing argparse | **21 / 28** | per-file grep |
| standalone .py missing header | **26 / 28** | per-file head grep |

## Mandatory category table — findings

| Category | Files audited | Findings | High | Med | Low |
|---|---|---|---|---|---|
| make-targets | 8 | 4 | 1 | 2 | 1 |
| cli-core | 11 | 5 (+1 exemplar) | 2 | 2 | 1 |
| cli-setup | 11 | 6 | 0 | 1 | 5 |
| cli-misc | 11 | 4 | 1 | 1 | 2 |
| scripts-py (set 1) | 13 | 9 | 1 | 2 | 6 |
| scripts-py (set 2) | 15 | 11 | 5 | 2 | 4 |
| scripts-sh | 13 | 7 | 0 | 1 | 6 |
| hooks | 90 | 12 | 0 | 1 | 11 |
| tests | 253 | 3 | 0 | 2 | 1 |
| **TOTAL** | — | **61** | **10** | **14** | **37** |

Exemplar (no defect — the reference all others should follow): `src/cli/verify_since_edit.py` — streams
per-suite `[done/total] ✓/✗` ticks, handles `TimeoutExpired` → exit 124, `--format json`, precise exit code.

---

## Grouped implementation checklist (8 batches, 61 items)

### Batch 1 — Greenwashing gates: commands that falsely report SUCCESS [P0 · 11 items]
> These break CI/verify trust — a green result that hides a real failure.

- [ ] **`make test-mcp`** (HIGH) — `server.py --test 2>&1 | grep -E "PASS|FAIL"` runs under `/bin/sh` (no pipefail) → recipe exit = grep's, so a FAIL line still exits 0. **`make verify` reports success on a failing MCP self-test.** Fix: capture to tmp, `grep -q FAIL && exit 1`, or `set -o pipefail` + server non-zero on FAIL.
- [ ] **`src/cli/main.py` `init`** (HIGH) — DB-init subprocess `capture_output=True`, returncode unchecked → prints "Initialized" + scaffolds on a broken DB. Fix: check returncode, surface stderr, `sys.exit`.
- [ ] **`src/cli/update.py` `update`** (HIGH) — `_run_db_migrations` `check=False`+`capture_output=True`, discards returncode/stdout/stderr → failed migration silent, still prints "Update applied." Fix: check + surface + reflect in exit.
- [ ] **`make docs-lint`** (MED) — `docs-lint.sh --quiet || true` then unconditional "docs-lint: OK"; `docs-lint.sh` `exit 0` on staleness unless `COS_DOCS_LINT_STRICT=1`. Fix: drop `|| true`, propagate, word OK honestly.
- [ ] **`src/cli/sync_all.py` `sync-all`** (MED) — per-adapter install failure captured to a note but exit stays 0. Fix: failure flag → `sys.exit(non-zero)`.
- [ ] **`src/cli/db_reset.py` `db-reset`** (MED) — post-wipe `graph-reindex` `check=False`, only catches `FileNotFoundError` → non-zero reindex reported as success; partial backup left on mid-loop fail.
- [ ] **`src/scripts/populate_board_from_phases.py`** (MED) — `main()` returns 0 even when `_create()`/`_set_emergency()` failed; conn not closed on exception. Fix: failure count → exit 1, `try/finally`.
- [ ] **`tests/test_anatomy_contract.py`** (MED) — `test_forbids_writing_in_references_real_subtrees` `warnings.warn()`s violations instead of asserting → **test can never fail.** Fix: `assert not issues`.
- [ ] **`make audit`** (LOW) — prints drift counts but exits 0 regardless; report-only. Fix: `exit 1` when any count >0, or rename to signal intent.
- [ ] **`src/scripts/prune_deleted_path.py`** (LOW) — per-path `sqlite3.Error` caught+continue but `main` returns 0. Fix: return 1 if any path errored.
- [ ] **`src/core/graph_os/tests/test_bench.py`** (LOW) — `test_result_serialisable` relies only on `json.dumps` raising; add an explicit shape assertion.

### Batch 2 — Stale `src/`-reorg paths: silently broken scripts & CI gates [P0 · 8 items]
> Systemic: the `src/` reorg left these pointing at non-existent `core/` (real path `src/core/`). High-confidence mechanical fix.

- [ ] **`src/scripts/verify_dispatchers.py`** (HIGH) — `REGISTRY = REPO_ROOT/'core'/'hooks'/registry.yaml` → `FileNotFoundError`. The `make verify-dispatchers` drift gate is an **always-erroring no-op.** Fix: prefix all paths with `src/`.
- [ ] **`src/scripts/smoke_doc_header.py`** (HIGH) — `parent.parent.parent/'core'/'thinking_os'` → `ModuleNotFoundError` on import. Fix: `…/'src'/'core'/…`.
- [ ] **`src/scripts/smoke_db_connections.py`** (HIGH) — `sys.path.insert(REPO_ROOT/'core')` → all imports fail → false DIVERGED/FAIL rows. Fix: `REPO_ROOT/'src'/'core'`; also `--db` env override.
- [ ] **`src/scripts/smoke_uid_resolver.py`** (HIGH) — `ROOT/'core'` + top-level import → uncaught `ImportError`. Fix: `ROOT/'src'/'core'`.
- [ ] **`src/scripts/smoke_sdk_dispatch.py`** (HIGH) — `REPO/'adapters'…` + `REPO/'core'…` → `spec` None → `AttributeError`. Fix: `REPO/'src'/…`; repair garbled docstring.
- [ ] **`src/scripts/operational_eval.py` (`make eval-operational`)** (MED) — `_step_mcp_selftest` builds `REPO_ROOT/'core'/'thinking_os'/server.py` (missing `src/`) → step always FAIL → `run_all` exits 1 every run. Fix: add `src/`.
- [ ] **`src/scripts/verify_phase_c_e2e.py`** (MED) — inconsistent: spawns `core.thinking_os.task_sync` + injects `/core/thinking_os` (no `src/`) while line 333 correctly uses `/src/scripts` — incomplete migration → `ModuleNotFoundError`. Fix: unify on `src/`.
- [ ] **`src/scripts/probe_agent_session_resolver.py`** (HIGH) — hardcoded *relative* `src/core/thinking_os/server.py` (no `Path(__file__)` anchor) → only runs from repo root; + dead spec/mod, bare `open()` exec. Fix: anchor on `Path(__file__).resolve()`, drop dead code, `read_text()`.

### Batch 3 — Progress on genuinely slow ops [P1 · 7 items]
- [ ] **`src/cli/doctor.py` `doctor`** (HIGH) — 30+ checks incl. 30s MCP self-test, 20s launch, 2× full `rglob('*')`; **zero stderr until done → 30-60s frozen terminal.** Fix: per-category `[checking X…]` tick to stderr (mirror verify_since_edit).
- [ ] **`src/cli/graph_commands.py`** (MED) — `graph-index-{local,github,zip}` + `group sync` loop `dispatch()` per file (clone + tree-sitter, slow) with only a final line. Fix: `click.progressbar` (as `graph-reindex` does).
- [ ] **`src/cli/main.py` `eject`** (MED) — `os.walk` whole project copying symlink targets, no progress. Fix: periodic stderr tick.
- [ ] **`src/core/scripts/link-stack-skills.sh`** (MED) — stacks×skills symlink loop emits ZERO output. Fix: per-skill stderr line + final stdout count.
- [ ] **`src/cli/cron_commands.py` `cron run`** (LOW) — hands off to slow `nightly.main` with no start signal. Fix: one stderr line before call.
- [ ] **`src/cli/setup.py` `setup`** (LOW) — slow `make docs-index` in bare `except: pass`; no narration on timeout. Fix: narrow except + warn.
- [ ] **`src/scripts/migrate_embeddings_minilm_to_bge_m3.py`** (LOW) — verify `run_until_idle` logs per-batch, else long run is silent.

### Batch 4 — stdout = result / stderr = narration discipline [P1 · 6 items]
- [ ] **`src/scripts/bench_sdk_dispatcher.py`** (MED) — final JSON on stdout but PRECEDED by all narration on same stream → JSON pipe chokes. Fix: narration → stderr.
- [ ] **`src/cli/board_commands.py`** (MED) — text-mode mixes human `ERROR` with otherwise-parseable stdout. Fix: keep ERROR on stderr; document `--format json` for machines.
- [ ] **`src/core/hooks/verify-agent-system.sh`** (MED) — full OK/WARN/FAIL report + banner on stdout mixed with the `PASS|WARN|FAIL` summary. Fix: narration → stderr, summary-only on stdout.
- [ ] **`src/core/scripts/docs-lint.sh`** (LOW) — `ok()/info()` print `OK:/INFO:` to stdout. Fix: route to stderr.
- [ ] **`src/scripts/e2e_dispatch_tool.py`** (LOW) — verdict shares stdout with narration, only exit code is machine signal. Fix: stderr narration or final JSON.
- [ ] **`src/cli/hook_renderer.py`** (LOW) — `[hook-renderer] …` narration on stdout. Fix: → stderr.

### Batch 5 — Algorithm efficiency [P2 · 3 items]
- [ ] **`src/cli/graph_commands.py`** (MED) — per-file `dispatch()` re-opens a SQLite connection each iteration. Fix: one backend connection across the loop. (pairs with Batch 3 fix)
- [ ] **`src/core/scripts/docs-nav-fix.sh`** (LOW) — spawns fresh `python3` per file over ≤232 docs. Fix: collect then one batched python pass.
- [ ] **`src/scripts/rename_formulas_to_semantic.py`** (LOW) — `rglob` ×22 inside `FILE_RENAMES` loop (O(22n)). Fix: one walk → basename dict. (kept-for-reference script — defer)

### Batch 6 — Error-handling hardening: hook `pipefail` sweep + misc [P2 · 16 items]
- [ ] **13 hooks** missing full `set -euo pipefail` (have `set -eu`, no `-o pipefail`) — masked pipe failures. Surfaced offenders: `auto-reindex-shell-ops`, `auto-task-sync`, `check-doc-size`, `lint-task`, `remind-daily`, `enforce-graph-context`, `enforce-graph-first-read`, `enforce-rename-plan` (+ remainder of the 13). Enforcement-category hooks are highest priority. (`verify-agent-system`, `test-hooks` use `set -uo` intentionally — tally-and-continue — confirm before touching.)
- [ ] **`src/scripts/refactor_agent_dual_mode.py`** (MED) — file-MUTATING (`write_text` on every agent .md) with **no `--dry-run`**, hardcoded `AGENTS_DIR`, unguarded IO, `main` returns 0 on partial fail. Fix: add `--dry-run/--root` + guards + non-zero exit.
- [ ] **`src/scripts/audit_mcp_tools.py`** (LOW) — `init_db()` at import → raw traceback on missing DB before `main()`. Fix: move fixture into `main()`.
- [ ] **`src/cli/setup.py`** (LOW) — narrow the bare `except Exception` around `make docs-index` (also in Batch 3).

### Batch 7 — Dead surface removal [P2 · 2 items]
- [ ] **`src/core/hooks/verify-changed-file.sh`** — dead 6-line stub (merged into `enforce-doc-sync.sh`), still registered (registry.yaml ~L574). Fix: delete file + registry entry (`make regen-adapter-templates` after).
- [ ] **`src/core/hooks/doc-sync-reminder.sh`** — dead 6-line stub (merged), still registered (~L749). Fix: delete file + registry entry.

### Batch 8 — Header contract sweep (PURPOSE/INPUT/OUTPUT/DEPENDENCIES/NOTES) [P3 · ~37 files]
> Lowest severity, fully batchable, pure documentation. Mechanical: 11/13 standalone .sh + 26/28 standalone .py missing header; 6 CLI modules flagged (`hub_commands`, `adapter_registry`, `core_version`, `aggregator`, `registry`, `sync_all`). ~15 overlap Batches 1-3 (add header while fixing); net header-only ≈ 22 files.

- [ ] standalone .sh (4 surfaced: `log-latest`, `log-search`, `log-write`, `ref-resolve`; sweep the 11)
- [ ] standalone .py (surfaced: `migrate_embeddings`, `audit_mcp_tools`, `e2e_dispatch_tool`, `graph_demo`, `measure_token_baseline`, `prune_deleted_path`, `regen_doc_index`, `regen_doctor_schema`, `regen_rules`; sweep the 26)
- [ ] CLI modules (6 above)

---

## Priority order (recommended)

1. **Batch 1 + 2** (P0, 19 items) — these are *bugs*: lies + broken gates. Ship first, per-item commits.
2. **Batch 3 + 4** (P1, 13 items) — UX + machine-parseability.
3. **Batch 5 + 6 + 7** (P2, 21 items) — hardening + cleanup.
4. **Batch 8** (P3, ~37 files) — header sweep, single pass.

## Resume marker

discovery: COMPLETE (61 findings) · remediation: NOT STARTED · next: Batch 1 item 1 (`make test-mcp`).
