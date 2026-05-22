---
id: TASK-014
title: "branch-guard hardening — whitespace normalize + git -C/-c options + literal-string false positives"
swimlane: core
kind: feature
epic: null
labels: [governance, hooks, hardening, post-mortem-TASK-013]
status: icebox
priority: P3
appetite: "1d"
created: 2026-05-22
started: null
completed: null
agent_session: null
depends_on: [TASK-013]
blocked_by: []
references: []
---

# TASK-014: branch-guard hardening — whitespace normalize + git -C/-c options + literal-string false positives

**Outcome (one sentence):** Close branch-guard bypass vectors surfaced by TASK-013 reviewer: normalize whitespace (tab/double-space slip through), strip `git -C <path>` + `git -c k=v` global-option prefixes, decide policy on nested `sh -c "git ..."`, allow `git checkout .` (or document), and stop false-positives on literal strings inside grep/echo/log args by anchoring to command-start positions.

## Read First
- src/core/hooks/branch-guard.sh
- tests/test_branch_guard.py
- docs/tasks/TASK-013-extend-branch-guard-to-block-head-rewriting-ops-reset-checko.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** branch-guard in trunk mode
- **When** any of the bypass probes below is fed as `tool_input.command`
- **Then** the hook BLOCKs (exit 2) with the same remediation as the
  direct form, AND the false-positive probes are allowed (exit 0).

### Bypass probes that must BLOCK after this task
1. `git  reset HEAD~1` (double space)
2. `git\treset HEAD~1` (tab between git and reset)
3. `git -C /tmp reset HEAD~1`
4. `git -c core.editor=vi reset HEAD~1`
5. `sh -c "git reset HEAD~1"` / `bash -c "git reset HEAD~1"` (decide:
   block or document as out-of-scope)

### False-positive probes that must ALLOW
6. `grep 'git reset HEAD~1' docs/` (literal string in grep)
7. `echo 'do not run git reset HEAD~1'` (literal string in echo)
8. `git log --grep='git reset HEAD~1'` (literal in log search)
9. `git checkout .` (restore cwd) — OR document explicit anti-pattern
   with a redirect to `git restore .`.

### Doc updates
10. `git-workflow.md` safe-form table includes `git checkout HEAD~1 --
    foo.py` (restore from sha; HEAD does not move) — currently
    implicit, make it explicit.
11. Add a "mid-session cleanup" note: if an agent accidentally commits
    garbage, the trunk-safe undo is `git revert HEAD && git push`.

## Notes
Source: reviewer subagent of TASK-013 (commit `0edccc3`). Findings are
hardening — not a security boundary; dominant-case gate works.

## Work Log
