---
id: TASK-554
title: "Remediate 9 confirmed findings from session adversarial review (pr-mode + Git tab)"
swimlane: core
kind: bug
epic: pr-mode-hardening
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-claude-20260624-034200-e9e7
depends_on: []
blocked_by: []
references: []
---
# TASK-554: Remediate 9 confirmed findings from session adversarial review (pr-mode + Git tab)

**Outcome (one sentence):** Fix the 9 code-backed findings a 5-dimension adversarial review confirmed against 53dcb48d..HEAD: (1) submit circuit-breaker counts the resolved branch's session not the drifted process session; (2) cleanup refuses its destructive worktree-remove/branch-delete when the single resolved candidate isn't owned by the invoking session and that owner isn't provably offline (peer data-loss); (3) branch-guard blocks `git pull <remote> +x:protected` like the fetch arm; (5) git_settings_fields.py never raises on non-dict git_settings and (6) matches jq's fail-closed behavior on a non-list protected_branches; (7) InfoTip exposes its tip via aria-describedby+useId and (8) is Esc-dismissible when hover-opened; (9) the orphaned read-only comment at ConfigPage EOF is removed; (4) block-shared-tree-edit falls back to a robust realpath when the parent dir is missing.

## Read First
- src/cli/pr_commands.py
- src/core/hooks/_helpers/branch_guard_check.py
- src/core/hooks/_helpers/git_settings_fields.py
- src/core/hooks/block-shared-tree-edit.sh
- src/core/web/ui/src/pages/ConfigPage.tsx

## Repro Steps
A 5-dimension adversarial Workflow review of 53dcb48d..HEAD produced 10 findings; 9 were independently verified (each verifier quoted live code; #3 and #5/#6 reproduced empirically). Full report in the session work-log. The 1 refuted finding (COS_STATE_DIR divergence) is paper-only and out of scope.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a submit under session-id drift where the resolved branch's session tail differs from the process session, **When** the open-PR circuit breaker runs, **Then** it counts open PRs against the resolved branch's session so the cap is not bypassed.
- **Given** a cleanup under drift that resolves a single same-slug worktree whose branch session ≠ the invoking session and whose owner is not provably offline, **When** the non-force destructive path runs, **Then** it refuses with a clear message (no peer worktree/branch destruction).
- **Given** `git pull <remote> +x:main` or `:production` in pr-mode, **When** the branch guard evaluates it, **Then** it BLOCKS pr-protected-ref identically to the fetch arm.
- **Given** a non-dict git_settings or a non-list protected_branches in hub-settings.json, **When** git_settings_fields.py runs, **Then** it returns cleanly without raising and matches jq's fail-closed result.
- **Given** the InfoTip popover, **When** a screen-reader or keyboard user interacts, **Then** the tip text is announced via aria-describedby (useId) and Esc closes it even when opened by hover; the orphaned read-only comment at EOF is gone.

## Work Log
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit branch_guard_check.py
- 2026-06-24 [claude]: Edit git_settings_fields.py
- 2026-06-24 [claude]: Edit block-shared-tree-edit.sh
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit test_branch_guard.py
- 2026-06-24 [claude]: Edit test_hub_settings_git.py
- 2026-06-24 [claude]: Edit test_cli.py
- 2026-06-24 [claude]: commit 470aeeae4c — fix(pr-mode): cap counts resolved branch session + cleanup refuses live-peer worktree under drift
- 2026-06-24 [claude]: commit facfa390cf — fix(pr-mode): branch-guard blocks pull colon-refspec; git_settings helper fails closed like jq
- 2026-06-24 [claude]: commit 144fcf0a89 — fix(hub): InfoTip a11y (aria-describedby + Esc-dismiss); drop orphaned read-only comment
- 2026-06-24 [claude]: Fixed all 9 confirmed review findings. Key non-obvious call: finding 2's ownership gate must refuse ONLY on…
