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
| 1 | Learning-loop memory corruption | TASK-104 | decay.py/learning.py/session_enrich.py/nightly.py | 4 | 5 | no | 5 | no | (pending) |
| 2 | Danger/secret regex holes | TASK-105 | block-dangerous-commands.sh/block-secrets.sh | 2 | 5 | no | 5 | no | (pending) |
| 3 | Per-panel marker-scope drift | TASK-107 | nudge-*/session-end/warn-abandoned/capture-work-log/cos-env | ~9 | 8 | no | 8 | no | (pending) |
| 4 | Board transition atomicity | TASK-108 | workflow.py/mcp_tools.py/4 hook helpers | 6 | 2 | no | 2 | no | (pending) |
| 5 | Memory-load correctness | TASK-109 | session-context.sh/learning.py/enforce-memory-check/memory.py | 4 | 5 | no | 5 | no | (pending) |
| 6 | Codex now-fixable parity | TASK-110 | codex-*-dispatch.sh/adapter.yaml/hook_renderer.py | 3 | 3 | no | 3 | no | (pending) |
| 7 | Hub learning panel | TASK-111 | scheduled.py/SettingsPage.tsx/MemoryPage.tsx/api-types | 4 | 4 | no | 4 | no | (pending) |
| 8 | Data-driven adapter detection | TASK-112 | cos-env.sh/doctor.py/test_no_hardcoded_stacks.py | 3 | 4 | no | 4 | no | (pending) |
| 9 | Hot-path Pre/Post dispatcher | TASK-113 | registry.yaml/hook_renderer.py/test-first/auto-regen-doc-index/dead stubs | ~6 | 6 | no | 6 | no | (pending) |
| 10 | enforce-anti-ambiguity dead gate | TASK-114 | enforce-anti-ambiguity.sh/cognition.py | 2 | 2 | no | 2 | no | (pending) |

## Per-Stream Implementation Checklist

> Status markers: ⬜ todo · 🟦 in-progress · ✅ done+verified. Update the category-table `Verified` cell + call `cos_supervise_record_output` on each stream close.

### Stream 1 — TASK-104 · Learning-loop memory corruption (P0, isolated from concurrent work)
- ✅ 1a CRIT — `learning.py` `_upsert_pattern` INSERT stamps `last_validated`+`last_accessed_at`=CURRENT_TIMESTAMP so fresh patterns aren't aged to 999d → archived on first decay. **DONE commit d69a52b + regression test (test_decay.py TestFreshPatternSurvivesFirstDecay).**
- ⬜ 1b HIGH — `decay.py:160-170` hard-delete prune must not erase below-floor knowledge without an `archived_at` grace (add column or gate on archived-duration, not at-floor).
- ✅ 1c MED — `learning.py` re-extract of an archived pattern resets `promoted_to=NULL` (revive) + refreshes last_accessed_at. **DONE commit d69a52b.**
- ⬜ 1d HIGH — `session_enrich.py:235-240` decay acquires the same `flock` nightly uses (concurrent-decay race).
- ⬜ 1e HIGH — unify decay marker path across nightly/auto-brain-decay/session_enrich (project-scoped `.last-decay`, not divergent COS_STATE_DIR vs project_root).
- ⬜ 1f MED — cron (`nightly.py`) regenerates digest after extract/decay (digest currently SessionStart-only → stale for cron-only projects).
- ⬜ 1g MED — Linux scheduler path (systemd user timer / documented crontab) OR remove the per-project `hour` knob that one global launchd job ignores.

### Stream 2 — TASK-105 · Danger/secret regex (P0, isolated)
- ⬜ 2a CRIT — `block-dangerous-commands.sh:50` rm -rf matches `/`,`.`,`..`,`./`,`*` and flag-order (`-fr`,`-r -f`); drop trailing `\b`, anchor on whitespace/EOL.
- ⬜ 2b HIGH — `block-secrets.sh:112` `sk-` regex tightened so kebab slugs/SKUs don't false-fire.
- ⬜ 2c MED — `block-dangerous-commands.sh:30` force-push refspec `+main`/`+master`; anchor branch match.
- ⬜ 2d MED — `block-secrets.sh:17` `.env` add guard for `git add -A`/`.`/dir (or document git-hook is the real defense); `:48` skip-list match path segments not substrings.

### Stream 3 — TASK-107 · Per-panel marker-scope drift (P1)
- ⬜ 3a HIGH — nudge-thinking-os/nudge-docs-first markers write to `${COS_PANEL_DIR:-…}` to match session-context clear (else fire once/agent-lifetime).
- ⬜ 3b HIGH — nudge-graph-os/.graph-nudge + nudge-task-discovery/.task-nudge + track-discovery → panel-dir + added to session-context startup clear.
- ⬜ 3c HIGH — session-end + warn-abandoned-task read stdin, `cos_panel_upgrade_from_payload`, agent-dir fallback for session-id (else empty → silent no-op on Claude Stop).
- ⬜ 3d HIGH — capture-work-log.sh:34 reads `${COS_PANEL_DIR:-$COS_AGENT_DIR}/.task-current`.
- ⬜ 3e HIGH — `.intent.json` + 3 `.*-nudged` markers added to COS_PER_PANEL_FILES + routed via cos_state_path; producer/guardian path parity.
- ⬜ 3f LOW — `.task-mode` → per-panel (banner verbosity cross-panel leak); warn-graph-empty marker path align; sync-task-current upgrades panel id.

### Stream 4 — TASK-108 · Board transition atomicity (P1)
- ⬜ 4a HIGH — `workflow.py:221-471` wrap read+wip+update in `BEGIN IMMEDIATE` + `WHERE task_id=? AND status=?` CAS w/ rowcount check; `mcp_tools.py:809` pass `expected_from`.
- ⬜ 4b MED — task_sync.py/work_log_append.py/transition_gates_cli.py/wip_limit_check.py route through `database.get_connection` (WAL+busy_timeout).
- ⬜ 4c LOW — consume_override.py atomic flock; cos-env heartbeat-before-panel-upgrade transient ppid dirs.

### Stream 5 — TASK-109 · Memory-load correctness (P1)
- ⬜ 5a HIGH — digest re-injected on compact/resume (currently startup-only → lost after auto-compaction).
- ⬜ 5b HIGH — `learning.py:472` learn_suggest uses `complexity`+real `domain` (recall is relevance-blind today).
- ⬜ 5c HIGH — banner `_read_state` (session-context.sh:333) applies 120-min TTL → marks stale skill/gate/task (hallucination window); compact snapshot TTL on task/skill too.
- ⬜ 5d MED — enforce-memory-check marker stamped by a real cos_search (PostToolUse on the tool) OR downgrade the claim wording.
- ⬜ 5e LOW — cos_search defaults min_confidence=0.3/since_days=180; split read-reinforce (no confidence bump on raw search).

### Stream 6 — TASK-110 · Codex now-fixable parity (P1, infra)
- ⬜ 6a HIGH — codex-posttool-dispatch.sh adds auto-reindex-shell-ops + auto-prune-deleted-files (drift vs adapter.yaml → graph staleness/zombie rows).
- ⬜ 6b HIGH — codex-stop-dispatch.sh adds verify-completion-claim + prevent-premature-done (3-layer intent half-wired).
- ⬜ 6c MED — generate dispatcher for-loops from adapter.yaml::delegates OR parity test asserting set-equality (kills future drift).

### Stream 7 — TASK-111 · Hub learning panel (P1, infra — coordinate w/ TASK-102 logging in web)
- ⬜ 7a HIGH — SettingsPage `ScheduledStatus` type + render cron_a + per-project run-logs (last_run_at/tasks/failures).
- ⬜ 7b HIGH — POST `/api/scheduled/run` (calls nightly.run_project / learn_extract) — ~15 lines.
- ⬜ 7c HIGH — 'Run learning loop now' button wired to the POST.
- ⬜ 7d MED — scheduled_status Pydantic response_model so api-types isn't `unknown` (structural drift fix).

### Stream 8 — TASK-112 · Data-driven adapter detection (P2, infra)
- ⬜ 8a HIGH — cos-env.sh:78-96 reads adapter.yaml::runtime_env_markers (not hardcoded if/elif).
- ⬜ 8b HIGH — doctor.py:1207 loader_fns generalized/registered (Cursor MCP diagnostic silently skipped today).
- ⬜ 8c MED — test_no_hardcoded_stacks extended to src/core/hooks/*.sh.
- ⬜ 8d LOW — remove speculative GEMINI_* literals (cos-env.sh:126/146/193); cursor adapter.yaml misleading camelCase comment.

### Stream 9 — TASK-113 · Hot-path Pre/Post dispatcher (P2, FULL refactor — high blast radius, do LAST, coordinate w/ TASK-100)
- ⬜ 9a — single PreToolUse + single PostToolUse Write|Edit dispatcher (parse stdin once, fan out in-process) — cuts ~42 spawns/edit.
- ⬜ 9b — delete dead stubs verify-changed-file + doc-sync-reminder + registry entries + regen.
- ⬜ 9c HIGH — test-first-reminder debounced (no `find . -maxdepth 6` ×2 over ~6.2k files per edit).
- ⬜ 9d HIGH — auto-regen-doc-index.sh path resolves src/scripts/regen_doc_index.py (currently dead).
- ⬜ 9e MED — warn-mcp-down debounce + lightweight probe (don't spawn full MCP server on compact/resume).

### Stream 10 — TASK-114 · enforce-anti-ambiguity dead gate (P1)
- ⬜ 10a CRIT — cos_ambiguity_check writes `.ambiguity-cache` (PASS / FAIL:criteria) via panel state path on EXECUTE-phase check.
- ⬜ 10b HIGH — enforce-anti-ambiguity.sh FAIL branch `exit 2` (not `exit 1`); add `cos_require_or_skip jq`.

## Resume Marker

<!-- last_updated_row: 0 -->
<!-- next_unchecked_row: 1 -->
<!-- last_updated_at: 2026-06-05T00:00:00Z -->
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
