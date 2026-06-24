---
id: TASK-557
title: "Harden 3 confirmed pr-mode residuals: branch-guard double-prefix (D1), gh-api wrong-cwd (D4), reaper preserve commit-returncode (D2)"
swimlane: core
kind: bug
epic: pr-mode-hardening
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-claude-20260624-154810-74c2
depends_on: []
blocked_by: []
references: []
---
# TASK-557: Harden 3 confirmed pr-mode residuals: branch-guard double-prefix (D1), gh-api wrong-cwd (D4), reaper preserve commit-returncode (D2)

**Outcome (one sentence):** Three code-confirmed pr-mode residuals from the HEAD audit are closed: the branch-guard protected wall normalizes arbitrarily-nested ref prefixes; the required-check probe always reads the target repo; and the orphan reaper never force-removes a worktree whose uncommitted work could not be preserved.

## Read First
- src/core/hooks/_helpers/branch_guard_check.py
- src/cli/pr_commands.py
- docs/playbooks/pr-workflow.md

## Repro Steps
D1: _unqualify_ref (branch_guard_check.py:413-423) strips one refs/heads/ level → refs/heads/refs/heads/production survives the {production} membership test. D4: _has_required_check (pr_commands.py:194-204) runs `gh api repos/{owner}/{repo}/...` with no cwd, so the {owner}/{repo} placeholder resolves from os.getcwd(). D2: _preserve_reaped (pr_commands.py:693-709) ignores the commit returncode and _reap_one (944-978) force-removes the worktree unconditionally → a commit-fails-but-bundle-succeeds case loses uncommitted work while reporting work_safe.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** pr-mode with protected=[production], **When** `git push origin HEAD:refs/heads/refs/heads/production` or `git update-ref refs/heads/refs/heads/production HEAD` runs, **Then** branch-guard BLOCKs it (the nested prefix normalizes to production via a looped strip).
**Given** `cos pr submit --repo X` invoked from a different repo's cwd, **When** `_has_required_check` probes, **Then** the `gh api` call runs with cwd=X so it reads X's branch protection, not the cwd repo's.
**Given** a reaped worktree whose dirty-work capture commit fails, **When** `_reap_one` runs, **Then** the worktree is NOT force-removed and needs_attention is True (no silent loss); a fallback git identity is injected so the common unset-identity case still commits + bundles.

## Work Log
- 2026-06-24 [claude]: Edit branch_guard_check.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit test_branch_guard.py
- 2026-06-24 [claude]: Edit test_cli.py
- 2026-06-24 [claude]: commit 5f65cf19e5 — fix(pr-mode): harden branch-guard double-prefix, gh-api cwd, reaper preserve (D1/D4/D2)
- 2026-06-24 [claude]: Deliberation: D2 was deeper than the audit framed — found work_safe=recoverable-or-preserved is wrong because…
