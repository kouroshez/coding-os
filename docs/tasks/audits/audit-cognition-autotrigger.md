---
audit_id: cognition-autotrigger
task_id: TASK-055
status: in_progress
slug: cognition-autotrigger
created: 2026-06-01
owner: claude
epic: cognitive-telemetry
matched_exhaustive: [all, every]
matched_scope: [fix]
---

# Audit — Cognition Auto-Trigger (TASK-048 deferred read-arcs)

**Verdict:** TASK-048 fixed every *write-side* loop (compose writes `.roles`,
`learn_extract` mines success, `session_enrich` records a real model). It
explicitly **deferred the auto-trigger / read-back side** as speculative
(its D4 "Rule-15 compose enforcement", G6 b/c). That deferred side is the
true cause of both user complaints: the pipelines are plumbed but never
*fire automatically* and their output is never *read back*. The user has now
explicitly requested closing them, so they are in scope (Rule 22: a real
current caller now exists — the user directive).

Re-verified live 2026-06-01 against `.coding-os/coding-os.db` + on-disk code:
- `persona_selections` = 1 (a 2026-05-13 seed) → `cos_compose_chain` never auto-fires.
- `find .coding-os -name .roles` → 0 → Roles UI structurally empty.
- `learned_patterns.access_count` sum ≈ 1, `pattern_validations` = 0 → recall + reinforce arcs dead.
- `agent_metrics` 389 rows / 1 distinct tuple `(session,opus,success)`, `duration_ms=0` → no variance.
- `task_outcomes` 36/36 success → extractor can only mine tautologies (R2 — separately tracked, NOT re-fixed here; the negative-signal capture is a product decision deferred by TASK-048 and unchanged).

## Scope rule (Rule 22)

Build only the read-arc auto-triggers + surfacing + visibility the user asked
for. Do NOT re-build TASK-048's write side. Do NOT add speculative new tables
or enforcement gates. Reuse existing tools (`compose_chain`, `learn_suggest`,
`digest.regenerate`) — wire them into the hook layer, don't reimplement.

## Macro root causes (from the forensic report)

- **R1** cognition read/trigger verbs live in NO hook body — only in voluntary MCP tools the agent ignores. ← this audit fixes R1.
- **R2** every outcome signal is hardcoded/derived to `success` → zero variance. ← Group C fixes the *writer literal*; the deeper "capture real failures" is a product decision left to TASK-048's deferred note.

## Category table

| # | Group | Finding | Sev | Root cause (file:line) | Fix class |
|---|---|---|---|---|---|
| A1 | Roles | `cos_compose_chain` has no auto-trigger; Rule 15 is unenforced prose | CRIT | no hook calls it; `nudge-thinking-os.sh:105` only recommends | IMPLEMENT |
| A2 | Roles | composed chain never surfaced to user/agent in chat | HIGH | `session-context.sh` banner has no roles field | IMPLEMENT |
| A3 | Roles | `.roles` writer duplicated risk (hook + MCP) | — | factor shared writer to avoid drift | IMPLEMENT |
| B1 | Learning | `cos_learn_suggest` never auto-invoked (recall dead, access_count≈0) | CRIT | no UserPromptSubmit/Orient hook calls it | IMPLEMENT |
| B2 | Learning | `cos_learn_validate` never runs (pattern_validations=0) | HIGH | only a soft reminder, input-starved | IMPLEMENT |
| B3 | Learning | no always-active digest injected each session | HIGH | `digest.regenerate` exists, no hook runs it at startup | IMPLEMENT |
| C1 | Metrics | `session_enrich.py:151` hardcodes `outcome='success'` literal | HIGH | SQL literal, never a failure | IMPLEMENT |
| C2 | Metrics | `duration_ms` from session-id mtime collapses to 0 | MED | `session_enrich.py:131-135` | IMPLEMENT |
| D1 | UI | no Hub page/route lists learned_patterns + weights | MED | no `/api/patterns` route, no MemoryPage | IMPLEMENT |
| E1 | Integrity | `formula_id` accepts XML/tool-call fragments | LOW | `cos_supervise_record_output` no validation | IMPLEMENT |
| R2 | Learning | extractor input 36/36 success (no negative signal) | HIGH | product decision (TASK-048 deferred) | DEFER (documented) |

## Grouped implementation checklist

### GROUP A — Roles auto-trigger + surface [CRIT]
- [ ] A3: factor the `.roles`/`.role` writer into one helper `_helpers/roles_state.py::stamp_roles(chain, agent_dir)`; have `cos_compose_chain` (cognition.py) import it (kill the inline duplicate).
- [ ] A1: new hook `auto-compose-roles.sh` (UserPromptSubmit) → reads `.thinking_os-gate`; when COMPLICATED/COMPLEX and `.roles` stale/absent, runs `_helpers/auto_compose.py` which calls `formula_composer.compose_chain` with minimal TaskSignals (complexity + dims from the gate) and stamps `.roles` via the shared writer + emits `compose_done` trace.
- [ ] A2: `session-context.sh` — read `.roles` (panel-first) and add `roles=<lead>+N` to the pulse PARTS; add a `roles=` field to the formal USER_BANNER.
- [ ] Register `auto-compose-roles` in `registry.yaml`; `make regen-adapter-templates`; `bash src/adapters/claude/install.sh`.
- [ ] VERIFY: `make verify-hooks`; manual: synthetic COMPLICATED gate → hook stamps `.roles` → banner shows roles.

### GROUP B — Learning recall + validate + digest [CRIT/HIGH]
- [ ] B1+B3: extend the auto_compose helper (or a sibling `_helpers/recall_inject.py`) called from `session-context.sh` UserPromptSubmit to run `learn_suggest` for the gate's domain/complexity and inject top-k into `additionalContext`, AND persist to `.learn-suggestions` (so remind-learn-validate has input). Run `digest.regenerate` at SessionStart:startup and inject `digest.md` (already partly printed; ensure regenerate runs first).
- [ ] B2: `remind-learn-validate.sh` — when `.learn-suggestions` present at task-done, additionally nudge with concrete `cos_learn_validate(pattern_id=…)` lines (already does) — the real fix is B1 making `.learn-suggestions` non-empty. No new mechanism.
- [ ] VERIFY: `uv run --extra rag pytest src/core/thinking_os/tests/test_learning.py -q`; manual: prompt with COMPLICATED gate → `.learn-suggestions` written → context shows recall.

### GROUP C — Metrics variance [HIGH]
- [ ] C1: `session_enrich.py` — derive `outcome` from session state (completion_gap observations / `.intent` unmet → 'partial'/'rework', else 'success') instead of the literal; bind as param.
- [ ] C2: `session_enrich.py` — compute duration from a session-start marker timestamp vs now (fallback 0 only when no start marker).
- [ ] VERIFY: `uv run --extra rag pytest src/core/thinking_os/tests/ -q` + `python src/core/thinking_os/server.py --test`.

### GROUP D — Memory/patterns UI [MED]
- [ ] D1: add `/api/patterns` route in `web/routes/` (reuse the envelope) returning id, pattern, confidence, trust_tier, impact_score, times_validated, times_violated, access_count, last_validated; add a Hub `MemoryPage.tsx` consuming it (verify field names against the route — api-contract-discipline).
- [ ] VERIFY: `uv run pytest tests/test_cli.py -q` (route import) + `make ui-build`.

### GROUP E — formula_id integrity [LOW]
- [ ] E1: validate `formula_id` (regex `^[a-z0-9_]+$`) in `cos_supervise_record_output` before INSERT; reject with `fail("validation", …)`.
- [ ] VERIFY: `uv run --extra rag pytest src/core/thinking_os/tests/ -q`.

### Doc alignment (final)
- [ ] Update `src/core/rules/transparency-banner.md` (new roles field), `docs/governance/critical-rules.md` Rule 15 (now hook-enforced), `src/core/hooks/registry.yaml` count in CLAUDE.md, and any roles/learning doc that said "agent must voluntarily call".
- [ ] `make docs-lint`.

## Results (filled as groups land)

| Group | Before | After | Commit |
|---|---|---|---|
| A | `.roles` never written; persona_selections=1; no chat surface | `auto-compose-roles` hook composes+stamps on COMPLICATED/COMPLEX gate; `.roles` writer factored to `roles_state.stamp_roles`; banner shows `roles=` | (pending) |
| B | recall never auto-invoked (access_count≈0); digest.md never regenerated | auto_compose helper also runs learn_suggest→writes .learn-suggestions (feeds remind-learn-validate); digest_regen.py regenerates digest.md at SessionStart | (pending) |
| C | outcome hardcoded 'success' literal; duration_ms always 0 | session_enrich derives outcome (completion_gap→partial) + duration from observation time-span; both verified varied | (pending) |
| D | learned_patterns had no UI surface (only a health COUNT) | new /api/patterns route (patterns.py) + Hub MemoryPage.tsx (confidence/trust_tier/decay/validated/used) under Diagnostics→Memory; ui-build clean, 55 web tests pass | (pending) |
| E | formula_id accepted XML/tool-call fragments (1 corrupt row) | cos_supervise_record_output rejects non-`[a-z0-9_]+` via fail("validation",…); guard tested; 1210 thinking_os tests pass, MCP self-test PASS | (pending) |

## Verification summary (all groups)
- verify-hooks: clean (syntax + shellcheck)
- thinking_os pytest: 1210 passed
- MCP self-test: PASS (14 cognition tools registered)
- web routes: 55 passed (test_web_server + test_route_audits)
- ui-build: clean
- learning pytest: 59 passed
- helper smoke tests: roles compose+stamp, recall→.learn-suggestions, digest regen, metrics variance (success+partial), formula_id guard — all green

## Doc alignment (done)
- transparency-banner.md: added `roles=` banner field + per-field accuracy row.
- critical-rules.md Rule 15: now documents the auto-fire (auto-compose-roles.sh + roles_state.py).
- AGENTS.md: hook counts 82/75/24 → 83/77/28; Rule 15 one-liner notes auto-fire + banner roles=.
- TASK-055: Acceptance G/W/T filled + work log.

## Resume marker
ALL GROUPS DONE (A–E) + doc-alignment complete + all targeted verification green. Only remaining step is the git commit, blocked by a peer session's deadlocked git (PID 68590, NOT this session) holding .git/index.lock. Per user: peer left untouched; changes verified-but-uncommitted until the lock clears.
