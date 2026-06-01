---
audit_id: roles-selection-panelscope
task_id: TASK-057
status: in_progress
slug: roles-selection-panelscope
created: 2026-06-01
owner: claude
epic: cognitive-telemetry
matched_exhaustive: [all, every]
matched_scope: [fix]
---

# Audit — Role Selection Quality + Panel-Scope Coherence (TASK-055 follow-up)

**Verdict:** The TASK-055 auto-compose hook works mechanically but has two
real defect families surfaced by the post-merge code-review + the user's
"roles=analyst never changes" report:

- **F1 — Panel-scope mismatch (from code-review):** `.roles`/`.role` are
  written at AGENT level while `.roles-composed`/`.learn-suggestions` are
  registered as PER-PANEL files and reset at `$COS_PANEL_DIR`. Writer and
  reset/reader disagree on scope → cross-panel leak + files never cleared.
  Conflicts with the TASK-035/052 per-panel isolation contract.
- **F2 — Degenerate role selection (from user report + proven):** the hook
  feeds the composer only `complexity`+`dimensions`. With every other signal
  at default (`action='unknown'`, `domain=[]`, `novelty=0`, `scope_size='medium'`),
  ONLY `analyst` clears its `min_score` → **every** COMPLICATED/COMPLEX prompt
  composes the identical single-role chain `['analyst']`. Proven:
  ```
  COMPLICATED dims=1/3/5 → ['analyst']   (composer, single role)
  COMPLEX     dims=1/3/5 → ['analyst']
  ```
  Compounded by: even a multi-role chain would show `chain[0]` forever — there
  is NO active-role phase progression as the agent moves analyze→implement→review.
  So the banner is stuck at `roles=analyst` from first prompt to last.

The user is correct: an enterprise cognitive OS must (a) pick the RIGHT chain
per task from real prompt signals, and (b) advance the ACTIVE role as work
phases shift. Both are in scope.

## Scope rule (Rule 22)
Reuse existing machinery: `cos_classify_prompt` already extracts rich
`TaskSignals` from prompt text; `presence.py::_newest_marker` already solves
"newest cognitive marker across panels". Do NOT reimplement either. Make
`.roles` panel-scoped like every other cognitive marker (TASK-035 precedent),
not invent a new scoping scheme.

## Category table

| # | Family | Finding | Sev | Root cause (file:line) | Fix class |
|---|---|---|---|---|---|
| F1.1 | panel-scope | `.roles`/`.role` written agent-level; `.learn-suggestions` reset panel-level → writer/reset scope mismatch | HIGH | roles_state.py:26 (agent-dir) vs session-context.sh:115 (panel reset) | IMPLEMENT |
| F1.2 | panel-scope | two panels of same agent fight over one agent-level `.roles`; banner shows other panel's chain | HIGH | auto-compose-roles.sh:42 (.roles-composed panel) vs .roles (agent) | IMPLEMENT |
| F1.3 | panel-scope | `.learn-suggestions` writer (agent-dir) vs remind-learn-validate reader (`$COS_AGENT_DIR`) vs session-context reset (`$COS_PANEL_DIR`) — 3-way scope drift | HIGH | auto_compose.py:114 · remind-learn-validate.sh:45 · session-context.sh:115 | IMPLEMENT |
| F1.4 | panel-scope | Hub roles.py reads agent-level `.roles` → shows stale fossil when live state is panel-scoped | MED | roles.py:202-203 | IMPLEMENT (reuse `_newest_marker`) |
| F2.1 | selection | composer starved — only complexity+dims passed; every task → `['analyst']` | HIGH | auto_compose.py:51 (bare TaskSignals) | IMPLEMENT |
| F2.2 | selection | no prompt signals: hook never reads stdin prompt to derive action/domain | HIGH | auto-compose-roles.sh (no stdin read) | IMPLEMENT |
| F2.3 | selection | no active-role phase switch — banner always shows chain[0], never advances with work phase | HIGH | .role only ever = chain[0]; no PostToolUse advancer | IMPLEMENT |
| C1 | cleanup | `auto_compose._recall_patterns` duplicates server.py `_persist_learn_suggestions_safe` | LOW | reuse-first | IMPLEMENT |
| C2 | cleanup | cognition.py local `import re as _re` now redundant w/ module-level `import re` | LOW | dead-ish | DEFER (pre-existing, not introduced here) |
| C3 | cleanup | MemoryPage toFixed no null-guard | LOW | cols DEFAULT, low risk | IMPLEMENT (cheap) |

## Grouped implementation checklist

### FAMILY 1 — Panel-scope coherence [HIGH]
Decision (precedent TASK-035 + TASK-052): make `.roles`/`.role` **panel-scoped**
like every other cognitive marker; Hub reads newest-across-panels.
- [ ] F1.1/F1.2: `roles_state.stamp_roles` writes to `$COS_PANEL_DIR` when set, else `$COS_AGENT_DIR` (panel-first). Add `.roles`/`.role` to `COS_PER_PANEL_FILES` in cos-env.sh.
- [ ] auto-compose-roles.sh: pass `$COS_PANEL_DIR` (panel-first) as the target dir to auto_compose.py, not agent dir.
- [ ] F1.3: auto_compose `_recall_patterns` writes `.learn-suggestions` panel-first; remind-learn-validate.sh reads `${COS_PANEL_DIR:-$COS_AGENT_DIR}/.learn-suggestions` (match session-context reset scope). Already reset at panel — make writer+reader agree.
- [ ] session-context.sh banner: read `.roles` panel-first (it already resets there); add `.roles`/`.role` to the SessionStart clear list.
- [ ] F1.4: roles.py `/chain` reuses a `_newest_marker`-style read (agent_dir + panels/*) for `.roles`/`.role` so the Hub shows the live panel's chain, not a fossil.
- [ ] VERIFY: two synthetic panel dirs with different chains → banner/​Hub each show the live one; `make verify-hooks`; web tests.

### FAMILY 2 — Real role selection + phase switch [HIGH]
- [ ] F2.1/F2.2: auto-compose-roles.sh reads the prompt from stdin (`cos_read_stdin_bounded`), passes it to auto_compose.py; auto_compose calls `cos_classify_prompt`'s signal-extraction (or the underlying classifier) to build a RICH TaskSignals (action, domain, scope_size, novelty) — not just complexity+dims — before `compose_chain`. Result: chains vary by task (debug→debugger, security→security_auditor, docs→documenter, etc.).
- [ ] F2.3: active-role phase switch. A PostToolUse hook (extend existing or tiny new) advances `.role` along the composed chain based on tool usage: Write/Edit → `implementer` (if in chain); test/verify cmd → `reviewer`; default → chain lead. Banner `roles=` shows the ACTIVE role, with chain position (e.g. `implementer 3/4`).
- [ ] VERIFY: prompt "debug the failing auth test" → chain includes debugger/security_auditor, not bare analyst; after a Write, banner active role switches to implementer.

### Cleanup
- [ ] C1: `_recall_patterns` calls the shared `_persist_learn_suggestions_safe` (or a shared helper) instead of hand-writing the file.
- [ ] C3: MemoryPage `toFixed` null-guards (`(p.confidence ?? 0).toFixed(2)`).

### Doc alignment (final)
- [ ] transparency-banner.md: `roles=` is the ACTIVE role + position, not the static lead. state-files.md: `.roles`/`.role` now panel-scoped.
- [ ] critical-rules.md Rule 15: note rich-signal composition + phase switch.
- [ ] `make verify-hooks` + targeted pytest + `make docs-lint`.

## Results (filled as families land)

| Family | Before | After | Commit |
|---|---|---|---|
| F2 | every COMPLICATED/COMPLEX task → identical `['analyst']`; banner frozen at chain[0] | `signals_from_prompt` derives action/domain/scope → chains vary (debug→debugger, audit→security_auditor, refactor→refactorer…); `advance-role.sh` advances `.role` by work phase; banner shows `roles=<active> N/M` | (pending) |
| F1 | `.roles`/`.role`/`.learn-suggestions` agent-scoped while reset/markers panel-scoped → cross-panel leak | all panel-first (writer + reader + reset + per-panel-files); Hub roles.py reads newest-across-panels via `_newest_marker` | (pending) |
| Cleanup | MemoryPage `toFixed` unguarded | `(x ?? 0).toFixed`; C1 left intentionally (panel-scope path differs from server.py helper — forcing reuse would re-introduce agent-scope bug) | (pending) |

## Verification summary
- thinking_os pytest: 1210 passed · verify-hooks clean · adapter suite 47 passed · golden parity 6 passed · web 31 passed · ui-build clean
- E2E proven: debug prompt → debugger chain; pytest → active role advances to reviewer; banner `roles=reviewer 2/3`.

## Resume marker
ALL FAMILIES DONE (F2, F1, cleanup) + verified. Pending: commits + doc-align (banner active-role format, Rule 15, state-files.md panel-scope).
