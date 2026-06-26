---
id: TASK-581
title: "Config\u2192Git tab audit fixes: per-project settings isolation, unknown-section data-loss, atomic write, fail-open surfacing, autonomy validation, enable-confirm + meta hard-block"
swimlane: core
kind: bug
epic: multi-agent-pr-mode
labels: [hub, pr-mode, git-settings, audit-fix, data-loss, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-26
started: 2026-06-25
completed: 2026-06-25
agent_session: ses-claude-20260625-203131-6294
depends_on: []
blocked_by: []
references: []
---
# TASK-581: Config→Git tab audit fixes: per-project settings isolation, unknown-section data-loss, atomic write, fail-open surfacing, autonomy validation, enable-confirm + meta hard-block

---
id: TASK-581
title: "Config→Git tab audit fixes: per-project settings isolation, unknown-section data-loss, atomic write, fail-open surfacing, autonomy validation, enable-confirm + meta hard-block"
swimlane: core
kind: bug
epic: multi-agent-pr-mode
labels: [hub, pr-mode, git-settings, audit-fix, data-loss, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-06-26
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-581: Config→Git tab audit fixes

**Outcome (one sentence):** The Hub Config→Git settings path is correct, durable, and honest end-to-end: writes go to the project bound by the /api/p/<slug>/ URL (not the Hub process env); unknown on-disk sections survive a PATCH; hub-settings.json is written atomically under a lock; every silent fail-open-to-trunk path emits an operator-visible warning; autonomy_level is validated where it is consumed; enabling pr-mode requires confirmation and is hard-blocked on the meta-repo; and the agent-only enforcement boundary is documented.

## Read First
- src/core/web/routes/settings.py
- src/core/web/_project_context.py
- src/core/hooks/cos-env.sh
- src/core/hooks/_helpers/git_settings_fields.py
- src/cli/pr_commands.py
- src/core/web/ui/src/pages/ConfigPage.tsx
- docs/architecture/adr/0013-pr-mode-multi-agent-git-workflow-consumer-only.md
- docs/playbooks/pr-workflow.md

## Repro Steps
Live on this repo: `jq -r 'keys' .coding-os/hub-settings.json` → [budget_cap, task_closure, trace_rotation]; `grep -c task_closure src/core/web/routes/settings.py` → 0. _load() iterates only _DEFAULTS so the next PATCH from any tab deletes task_closure. _settings_path() (settings.py:38) reads os.environ[COS_STATE_DIR] while sibling routes (95/121/149/167) use current_project_root() → multi-project Hub clobber. _save() (settings.py:56-59) is a non-atomic write_text.

## Acceptance (G/W/T) — *this IS the Definition of Done*

**Given** the Hub Config→Git tab and its settings/hooks/cli/ui path, **When** the fixes below land, **Then** every numbered criterion holds and each changed subsystem's matrix test is green.

- **Given** a multi-project Hub **When** GET/PATCH /api/p/<slugA>/settings **Then** _settings_path() resolves to slugA's .coding-os/hub-settings.json via current_project_root() (env only outside request scope); a test asserts two slugs write two files. [C1]
- **Given** hub-settings.json with an unknown section (task_closure) **When** any PATCH lands **Then** the unknown section is preserved; regression test asserts survival. [C2]
- **When** _save runs **Then** it writes tmp+fsync+os.replace and patch_settings holds an exclusive lock across load→merge→save; a concurrent reader never sees a torn/empty file. [H1]
- **Given** a present-but-unparseable file **When** PATCH lands **Then** it refuses (409) instead of clobbering with all-defaults. [M9]
- **When** the git_settings key is present but parsing yields nothing, OR an inherited COS_GIT_WORKFLOW=trunk conflicts with file enabled=true, **Then** cos-env.sh emits a one-time stderr warning (precedence unchanged). [M1+H4]
- **Given** identical JSON fixtures (absent/null/[]/non-list protected_branches) **When** fed through the jq filter and git_settings_fields.py **Then** the TSV is byte-identical (parity test). [M3]
- **When** _autonomy_level reads an unknown rung **Then** it falls back to draft with a logged warning (covers non-API writes). [M2]
- **Given** autonomy auto_merge/autonomous **When** submit finds no required check **Then** it escalates the board task to blocked (reuse _escalate_blocked), not a silent stderr line. [H3]
- **When** a user enables pr-mode **Then** a confirm dialog appears, enabling is hard-blocked for slug==coding-os, and after Save the form re-seeds from the server response. [H5]
- **When** the Git tab is open **Then** the git-state capability probe fires regardless of enabled so config is not blind. [M8]
- **Then** ADR-0013 + pr-workflow.md document the agent-only enforcement boundary and the Git tab shows a static caution that the policy binds the agent, not human/plain-git. [H2]

Tests: web-routes pytest · `make verify-hooks` · `tests/test_cli.py` · ConfigPage vitest · `make docs-lint`. Docs+code co-edited (Rule 0/19). M4 (Codex edit-isolation) already accepted in TASK-551 — not reopened.

## Work Log
- 2026-06-26 [claude]: Edit settings.py
- 2026-06-26 [claude]: Edit settings.py
- 2026-06-26 [claude]: Edit settings.py
- 2026-06-26 [claude]: Edit test_hub_settings_git.py
- 2026-06-26 [claude]: Edit test_hub_settings_git.py
- 2026-06-26 [claude]: commit 0a1c48ce7e — fix(hub): scope Config→Git settings per-project + preserve unknown sections + atomic write
- 2026-06-26 [claude]: Group A (settings.py route) done + green: C1 project-scoped _settings_path, C2 _load preserves unknown sections…
- 2026-06-26 [claude]: Edit cos-env.sh
- 2026-06-26 [claude]: Edit test_hub_settings_git.py
- 2026-06-26 [claude]: Edit test_hub_settings_git.py
- 2026-06-26 [claude]: commit 49be78abf6 — fix(hooks): surface git_settings fail-open downgrades + jq↔python parity test
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit test_cli.py
- 2026-06-26 [claude]: commit d9c47e24e8 — fix(pr): validate autonomy_level at consumption + escalate auto-merge deadlock
- 2026-06-26 [claude]: Group B + C done + green. B: cos-env.sh debounced warnings for unreadable git_settings (M1) + trunk-override…
- 2026-06-26 [claude]: commit 08c658a266 — fix(hub-ui): confirm pr-mode enable + meta hard-block, always-probe, agent-only note
- 2026-06-26 [claude]: Edit 0013-pr-mode-multi-agent-git-workflow-consumer-only.md
- 2026-06-26 [claude]: Edit pr-workflow.md
- 2026-06-26 [claude]: Edit pr-workflow.md
- 2026-06-26 [claude]: Edit pr-workflow.md
- 2026-06-26 [claude]: commit 7b8d9d8606 — docs(pr-mode): document agent-only enforcement boundary + settings durability
- 2026-06-26 [claude]: Group D+E done + full verification green. D (ConfigPage.tsx): H5 confirm-step + meta-repo hard-block + form re-seed…
