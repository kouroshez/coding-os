---
audit_id: hook-system-remediation-2026-06-05
task_id: TASK-104
status: in_progress
created: 2026-06-05
---

# Hook-System Remediation — 17-Agent Reverse-Engineering Audit

**Source findings:** 17-agent workflow (wka4h1afk) — 90 hook scripts (84 registered) + memory/cron/adapter/UI systems. Full raw findings: workflow output `tasks/wka4h1afk.output` (271 KB); curated digests `tool-results/buzsf9gr9.txt` (critics) + `b6mwk1h0e.txt` (systems). Totals: **4 critical · ~27 high · 26 medium · 31 low** (149 incl. systems).

**Matched exhaustive:**  ·  () ·
**Matched scope:** fix · verify · audit
**Predicates:** every category row `Verified=yes` + `Hits after=0`; per-fix test+verify; per-fix commit; do NOT break concurrent agents (TASK-100 scripts/hooks output-quality, TASK-102 web/cli logging are LIVE).

## Categories — Mandatory Coverage Table (10 remediation streams)

| # | Category (stream) | Task | Pattern / scope | Files scanned | Hits before | Fixed | Hits after | Verified | Evidence (commit / file:line) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Learning-loop memory corruption | TASK-104 | decay.py/learning.py/session_enrich.py/nightly.py/cron_commands.py | 5 | 7 | yes | 0 | yes | d69a52b·568c4d9·b227b83·d752bd7·7096979 (auto-brain marker→N9, hour knob→N7) |
| 2 | Danger/secret regex holes | TASK-105 | block-dangerous-commands.sh/block-secrets.sh/_helpers/check_dangerous_rm.py | 3 | 4 | yes | 0 | yes | 10d1240·2d6b7de (25 hook behavior tests) |
| 3 | Per-panel marker-scope drift | TASK-107 | nudge-*/session-end/warn-abandoned/capture-work-log/cos-env | ~9 | 8 | yes | 0 | yes | 25d38fd (25 files; panel-scope smoke 1-4 pass; 0 new test-hooks failures vs baseline 60/67) |
| 4 | Board transition atomicity | TASK-108 | workflow.py/4 helpers/consume_override | 6 | 2 | yes | 0 | yes | e937785 (388 board tests + CAS-conflict smoke; expected_from subsumed by under-lock re-verify) |
| 5 | Memory-load correctness | TASK-109 | session-context.sh/learning.py/enforce-memory-check/server.py | 4 | 5 | yes | 0 | yes | 863d3d7 (digest-startup + boost smoke + gate-TTL unit + 142 learning/memory tests + MCP self-test) |
| 6 | Codex now-fixable parity | TASK-110 | codex-*-dispatch.sh/adapter.yaml/test_adapter_parity.py | 3 | 0 | yes | 0 | yes | 5bbb8a6 (6a wired + 6c parity test 5/5; 6b refiled TASK-153 — exit-0-stdout drop, no silent no-op) |
| 7 | Hub learning panel | TASK-111 | scheduled.py/SettingsPage.tsx | 4 | 0 | yes | 0 | yes | 27deb9f (route+model registered, tsc 0 errors; hour-knob fold-in deferred) |
| 8 | Data-driven adapter detection | TASK-112 | doctor.py/cos-env.sh | 3 | 0 | yes | 0 | yes | 6e96f5c (cursor loader smoke + 633 no-hardcoded tests; 8a/8c→TASK-155) |
| 9 | Hot-path Pre/Post dispatcher | TASK-113 | test-first/warn-mcp-down/auto-regen-doc-index/auto-brain-decay | ~6 | 0 | yes | 0 | yes | d7004d6·d08c282 (debounce+path smokes; 9a/9b/5d-autostamp→TASK-161 golden-window) |
| 10 | enforce-anti-ambiguity dead gate | TASK-114 | enforce-anti-ambiguity.sh/cognition.py | 2 | 2 | yes | 0 | yes | 1290412 (DB-state gate + clear-on-pass test) |

## Per-Stream Implementation Checklist

> Status markers: ⬜ todo · 🟦 in-progress · ✅ done+verified. Update the category-table `Verified` cell + call `cos_supervise_record_output` on each stream close.

### Stream 1 — TASK-104 · Learning-loop memory corruption (P0, isolated from concurrent work)
- ✅ 1a CRIT — `_upsert_pattern` INSERT stamps `last_validated`+`last_accessed_at` so fresh patterns aren't archived on first decay. **DONE d69a52b + regression test.**
- ✅ 1b HIGH — `archived_at` (migration v33) — prune gates on time-since-archived so freshly-archived knowledge gets full grace. **DONE 568c4d9 + grace tests.**
- ✅ 1c MED — re-extract revives archived pattern (`promoted_to=NULL`, `archived_at=NULL`) + refreshes recency. **DONE d69a52b / 568c4d9.**
- ✅ 1d HIGH — `session_enrich` decay routes through shared `run_decay_locked` (flock). **DONE b227b83 + throttle test.**
- ✅ 1e HIGH — decay marker unified at `<db-dir>/.last-decay` (mtime throttle, shared lock) for nightly + session_enrich. **DONE b227b83.** ↪ auto-brain-decay.sh marker alignment folded into N9 (avoids live TASK-100 hook collision).
- ✅ 1f MED — `nightly.run_project` regenerates digest after extract/decay. **DONE d752bd7.**
- ✅ 1g MED — Linux systemd `--user` .timer/.service scheduler; `cos cron install` dispatches by OS. **DONE 7096979 + tests.** ↪ misleading per-project `hour` knob removal folded into N7 (web layer).

### Stream 2 — TASK-105 · Danger/secret regex (P0, isolated)
- ✅ 2a CRIT — rm -rf now blocked via shlex-correct helper (`_helpers/check_dangerous_rm.py`) for `/`·`.`·`..`·`./`·`*`·`-fr`·`-r -f`·top-level abs·project dirs. **DONE 10d1240 + 19 tests.**
- ✅ 2b HIGH — `sk-` regex keyed on specific prefix (sk-ant-api##-/sk-proj-/40+ alnum) — kebab slugs no longer false-fire, real keys still caught. **DONE 2d6b7de + tests.**
- ✅ 2c MED — force-push refspec `+main`/`+HEAD:main` blocked. **DONE 10d1240 + tests.**
- ✅ 2d MED — secret skip-list matches path segments/basenames not substrings (`latest/`,`contest/` no longer silently unscanned). **DONE 2d6b7de.** ↪ `.env` git-add guard left best-effort by design — the installed git pre-commit hook scans the staged set (the real defense, per audit recommendation).

### Streams 3-6, 8 — DONE (detail in commits + task work logs)
- ✅ **N3 (TASK-107) 25d38fd** — 6 marker classes panel-scoped (nudge debounce, `.intent.json`, `.task-mode`, `.*-nudged`, capture-work-log, warn-graph-empty) + Stop hooks (session-end, warn-abandoned-task) upgrade panel id from stdin w/ agent-dir fallback. 25 files; smoke A-D + 0 new test-hooks regressions.
- ✅ **N4 (TASK-108) e937785** — `workflow.transition` write path = one `BEGIN IMMEDIATE` section: re-SELECT under lock + WIP-under-lock + CAS `UPDATE … WHERE status=?` (rowcount→transient) + MD-in-txn + rollback/raise. 4 helpers → `get_connection`; consume_override flock. `expected_from` subsumed by under-lock re-verify. 388 board tests + CAS smoke. (cos-env ppid-GC deferred — orphan-dir nicety.)
- ✅ **N5 (TASK-109) 863d3d7** — 5a digest on startup; 5b learn_suggest CASE-boost for complexity/task_type; 5c banner `⌛stale` gate TTL; 5d enforce-memory-check honest self-attest wording (auto-stamp→N9); 5e cos_search default min_confidence=0.3 + stale-reinforce-claim fix. 142 tests + smokes.
- ✅ **N6 (TASK-110) 5bbb8a6** — 6a codex posttool dispatcher wires auto-reindex-shell-ops + auto-prune-deleted-files (side-effect hooks); 6c parity test (for-loop == adapter.yaml). 6b (verify-completion-claim/prevent-premature-done) → **TASK-153**: they emit exit-0 stdout the dispatcher drops, so wiring = silent no-ops; needs Stop-dispatcher stdout-forwarding + codex-runtime verify.
- ✅ **N8 (TASK-112) 6e96f5c** — 8b doctor `loader_fns` maps `cursor_mcp_json`→`_load_claude_json` (Cursor MCP diagnostic no longer skipped); 8d drop speculative GEMINI_/ANTHROPIC_ session vars. 8a (data-driven cos-env detection via regen snippet) + 8c → **TASK-155** (hottest file; needs generator + per-adapter smoke).

### Stream 7 — TASK-111 · Hub learning panel — ✅ DONE 27deb9f
- ✅ 7a — SettingsPage `ScheduledStatus` enriched (cron_a + per-project `last_run_at`/`tasks`/`consecutive_failures`/errors); renders last-run + nightly-cron-loaded/next-run state. tsc 0 errors.
- ✅ 7b — `POST /api/scheduled/run/{slug}` → `nightly.run_project(proj, dry_run=False)` via `asyncio.to_thread` (off the event loop); fail-soft `RunResult{ran,error}`. Route registered (verified).
- ✅ 7c — "Run learning loop now" button in ScheduledMaintenanceSection wired to the POST + invalidates `/status`; shows running/ran/failed note.
- ✅ 7d — `scheduled_status` now declares `response_model=ScheduledStatus` (CronStatus + ProjectScheduled) — the OpenAPI contract is typed (api-types regen picks it up). ↪ misleading per-project `hour` knob removal DEFERRED: the field lives in ScheduledConfigForm (live Cortex-UI collision zone) + needs config.json migration; small follow-up, not worth the collision for a cosmetic knob.

### Stream 8 — TASK-112 · Data-driven adapter detection (P2, infra) — ✅ DONE 6e96f5c
- ⏭️ 8a — REFILED as TASK-155. cos-env's agent-detection if/elif (+ panel session-marker loop + model-env resolver) duplicates `adapter.yaml::runtime_env_markers`/`runtime_session_marker` (already the SSOT consumed by `cli/board_commands.py::_detect_agent_runtime`). The correct fix is a REGEN-generated `_agent-detect.generated.sh` sourced by cos-env (fast hot path, no per-hook YAML parse). cos-env.sh is sourced by EVERY hook of EVERY adapter — doing this needs a generator + regen wiring + byte-equivalence diff + per-adapter detection smoke, which is its own task, not a marathon-tail edit on the single most load-bearing file.
- ✅ 8b — doctor's `loader_fns` now maps `cursor_mcp_json` → `_load_claude_json` (Cursor `.cursor/mcp.json` shares the `mcpServers.coding-os` shape per cursor/install.sh). The Cursor `mcp.actually_launches` diagnostic stopped silently skipping (`spec.loader not in loader_fns`). Smoke: cursor loader resolves `.cursor/mcp.json`.
- ⏭️ 8c — bundled into TASK-155: extending `test_no_hardcoded_stacks` to `src/core/hooks/*.sh` can only go green once cos-env's literals come from the generated file (8a) — coupling them keeps the test from failing on the existing-and-correct hardcoded block.
- ✅ 8d — removed speculative `GEMINI_SESSION_ID`/`ANTHROPIC_SESSION_ID` from cos-env's panel session-marker loop + the Gemini comment (anti-overengineering; no shipping adapter exports them). Real claude/cursor/codex vars retained. 633 no-hardcoded tests + verify-hooks clean.

### Stream 9 — TASK-113 · Hot-path Pre/Post dispatcher — ✅ DONE (safe wins) d7004d6·d08c282
- ⏭️ 9a — REFILED **TASK-161**. The single in-process Pre/Post Write|Edit dispatcher (cuts ~42 spawns/edit) restructures registry.yaml + hook_renderer + every gate-hook invocation + a full golden re-capture across every stack×adapter — highest blast radius (breaks every edit if wrong). Needs a clean no-concurrent-session window + a per-gate block-regression test, not a marathon-tail edit.
- ⏭️ 9b — REFILED **TASK-161** (with 9a — same golden re-capture). Deleting the 2 dead no-op stubs (verify-changed-file.sh + doc-sync-reminder.sh) touches registry + generated templates + scaffold_manifest + test-hooks + 2 test files + dozens of `tests/golden/**` snapshots; for 6-line no-ops it's a cleanup, not a fix, so it rides with the dispatcher's golden pass.
- ✅ 9c — test-first-reminder debounced: reminds at most once per file per session via `${COS_PANEL_DIR}/.test-first-reminded/<key>` (cleared each SessionStart); the ~6k-file `find` no longer repeats on every edit. Smoke: 1st reminds (3 lines), 2nd silent.
- ✅ 9d — auto-regen-doc-index now lists `${PROJECT_ROOT}/src/scripts/regen_doc_index.py` first (was dead from a symlinked `.claude/hooks/` install). Smoke: no `script_missing`.
- ✅ 9e — warn-mcp-down debounced: skips the heavy spawn-probe when `<agent-dir>/.mcp-probe-ok` is fresher than `COS_MCP_PROBE_TTL` (default 600s) — no full-MCP-server respawn on every compact/resume. Smoke: skipped with fresh marker.
- ✅ fold (N1) — auto-brain-decay throttle marker → `<db-dir>/.last-decay` (shares decay.py/nightly marker; no double-run). The 5d memory-check auto-stamp (PostToolUse on cos_search) → **TASK-161** (new hook + registry + golden).

### Stream 10 — TASK-114 · enforce-anti-ambiguity dead gate (P1)
- ✅ 10a CRIT — gate made live via the canonical DB (more reliable than a producer-written file, which has the MCP-panel-resolution flaw): cos_ambiguity_check clears the session's prior `ambiguity_violations` each check (pass→none); the hook queries the table for the session. **DONE 1290412 + clear-on-pass test.**
- ✅ 10b HIGH — FAIL branch now `exit 2` (was `exit 1`); fail-open guards for missing sqlite3/DB/session. **DONE 1290412.**

## Resume Marker

<!-- last_updated_row: 9 -->
<!-- next_unchecked_row: 0 -->
<!-- last_updated_at: 2026-06-05T00:00:00Z -->
<!-- progress: ALL 10 streams closed (N1-N10). Safe fixes shipped; the registry/golden-heavy + unverifiable-without-runtime sub-items refiled as scoped tasks: TASK-153 (codex Stop stdout forward), TASK-155 (data-driven cos-env detection), TASK-161 (hot-path dispatcher + dead-stub + memory-check auto-stamp). -->
<!-- sequence: N1(104) → N2(105) → N10(114) → N3(107) → N5(109) → N4(108) → N6(110) → N8(112) → N7(111) → N9(113-last) -->

## Notes

- **Concurrency:** TASK-100 (scripts/make/hooks output-quality) + TASK-102 (web/cli logging) are LIVE on other sessions. Sequencing starts with thinking_os-isolated streams (1,2,10) then board/state (3,4,5), defers hot-path hook refactor (9) + hub UI (7) which overlap TASK-100/102 — coordinate via `git pull --rebase` + explicit-path commits, stage only my files.
- **Evidence model:** per-fix commit sha recorded in the category table Evidence cell; stream-close evidence via `cos_supervise_record_output`. Checkboxes are working notes; the guardian trusts the formula_dispatches DB rows, not the ticks.
- **WIP:** in_progress cap=1 held by a concurrent session — my stream task-starts use `bypass_wip` (user-authorized parallel work), one of MY streams in_progress at a time.

## Closing Checklist (guardian asserts)

- ⬜ Every category row `Hits after = 0` (or justified n/a)
- ⬜ Every category row `Verified = yes`
- ⬜ Every category row non-empty `Evidence`
- ⬜ EvidenceBundle via `cos_supervise_record_output`
- ⬜ Reviewer subagent re-grep zero
- ⬜ Frontmatter `status: completed` + completed date
