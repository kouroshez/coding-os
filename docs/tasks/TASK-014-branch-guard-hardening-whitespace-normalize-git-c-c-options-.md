---
id: TASK-014
title: "branch-guard hardening — whitespace normalize + git -C/-c options + literal-string false positives"
swimlane: core
kind: feature
epic: null
labels: [governance, hooks, hardening, post-mortem-TASK-013]
status: in_progress
priority: P3
appetite: "1d"
created: 2026-05-22
started: 2026-05-22
completed: null
agent_session: ses-claude-20260522-181701-790c
depends_on: [TASK-013]
blocked_by: []
references: []
---
# TASK-014: branch-guard hardening — whitespace normalize + git -C/-c options + literal-string false positives

**Outcome (one sentence):** Close branch-guard bypass vectors surfaced by TASK-013 reviewer — normalize whitespace (tab/double-space), strip `git -C <path>` + `git -c k=v` global-option prefixes, handle nested `sh -c`/`bash -c` invocations, allow `git checkout .` as a file-restore form, and stop false-positives on literal strings inside grep/echo/log args by anchoring matches to command-start positions instead of pure substring.

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

- 2026-05-22 — Lifted parsing out of bash into Python helper
  `src/core/hooks/_helpers/branch_guard_check.py`. The hook is now a
  thin wrapper (~40 LOC) that fast-skips if the command lacks `git`,
  then dispatches to the helper for a JSON verdict. The helper uses
  `shlex.split` for proper quote handling, normalizes whitespace,
  strips `git -C` / `git -c` / `--git-dir=` / `--work-tree=` global
  options, extracts nested `sh -c` / `bash -c` / `zsh -c` invocations,
  and splits on shell separators so a `git` token inside an `echo` /
  `grep` arg is never treated as a git invocation. All 9 reviewer
  probes from TASK-013 now produce the expected verdict (5 previously-
  bypassed cases block, 4 previously-false-positives allow). 16 new
  tests added (45 total). Adapter + golden parity green.
- 2026-05-22 (post-review fix) — Reviewer subagent of commit `7c21565`
  found 4 residual bypass patterns (doubly-nested `sh -c`, literal `\n`
  separator, `` `backtick` `` subshell, multi-level `bash -c "sh -c
  ...".`). Extended `_evaluate` with: depth-bounded recursion (cap=8)
  through `_extract_nested_shells` + new `_extract_backticks`; treat
  `\n` as a `;` separator BEFORE whitespace collapse. Added 5 tests
  (50 total). All TASK-013 + TASK-014 reviewer probes now match
  expected verdicts. Closed TASK-014 without spawning TASK-015 — the
  patterns are within the original task's threat class.
