---
id: TASK-612
title: "Close git long-option-abbreviation bypasses in branch-guard / block-secrets / block-dangerous-commands"
swimlane: infra
kind: bug
epic: git-foundation-hardening
labels: [pr-mode, branch-guard, git-safety, code-review, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-27
started: 2026-06-27
completed: 2026-06-27
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-612: Close git long-option-abbreviation bypasses in branch-guard / block-secrets / block-dangerous-commands

**Outcome (one sentence):** git resolves ANY unambiguous long-option prefix (--har→--hard, --no-veri→--no-verify, --for→--force), so three client-side L2 guards are bypassable by abbreviation; rewrite each to parse options by SHAPE/prefix (not a hardcoded literal set) — branch-guard `_check_reset` strips all leading option tokens incl. mode abbreviations and treats path-mode markers (`--`, `-p`, `--pathspec-from-file`) as safe; block-secrets `check_git_bypass` matches any prefix ≥ the `--no-verify` disambiguation point; block-dangerous-commands detects forced `git clean` via any `--f..` prefix / split clusters — closing the bypass class WITHOUT false-blocking ambiguous-too-short (`--no-ver`) or unrelated flags (`--no-verbose`, `reset -p -- path`).

## Read First
- src/core/hooks/_helpers/branch_guard_check.py
- src/core/hooks/_helpers/check_git_bypass.py
- src/core/hooks/block-dangerous-commands.sh
- tests/test_branch_guard.py

## Repro Steps
Workflow whdjyvqjq verified REAL (priority 72): `git reset --har HEAD~1` slips branch-guard (_check_reset strips only a hardcoded flag set); `git commit --no-veri -m x` slips block-secrets (check_git_bypass matches only literal --no-verify) and skips the commit-msg/pre-commit hooks; `git clean --for` / split `-d -f` slips block-dangerous-commands.sh:166 (greps literal `git clean ...-f`). Root cause: git accepts any unambiguous long-option prefix. Edit live-symlinked hook helpers via the atomic-edit protocol; commit per-hook (Rule 22), not one bundle.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** `git reset --har HEAD~1` or `git reset --so HEAD~2`, **When** branch-guard checks, **Then** it BLOCKs (HEAD-move) while `git reset -p` and `git reset -- file.py` stay ALLOWed. **Given** `git commit --no-veri` or `--no-verif`, **When** block-secrets checks, **Then** it BLOCKs while `--no-ver` (ambiguous; git itself rejects) and `--no-verbose` stay ALLOWed. **Given** `git clean --for` / `--f` / split `-d -f`, **When** block-dangerous-commands checks, **Then** it BLOCKs. Verify: `uv run pytest tests/test_branch_guard.py tests/test_block_secrets.py -q` + `make verify-hooks`, all green with the new regression cases.

## Work Log
- 2026-06-27 [claude]: Edit probe.py
- 2026-06-27 [claude]: Edit git_command_parse.py
- 2026-06-27 [claude]: Edit branch_guard_check.py
- 2026-06-27 [claude]: Edit branch_guard_check.py
- 2026-06-27 [claude]: Edit check_git_bypass.py
- 2026-06-27 [claude]: Edit check_git_destructive.py
- 2026-06-27 [claude]: Edit block-dangerous-commands.sh
- 2026-06-27 [claude]: Edit probe2.py
- 2026-06-27 [claude]: Edit test_branch_guard.py
- 2026-06-27 [claude]: Edit test_branch_guard.py
- 2026-06-27 [claude]: Edit test_branch_guard.py
- 2026-06-27 [claude]: Edit test_hooks.py
- 2026-06-27 [claude]: Edit test_hooks.py
- 2026-06-27 [claude]: Edit test_hooks.py
- 2026-06-27 [claude]: Edit probe_live.py
- 2026-06-28 [claude]: Inherited a complete impl from crashed session 30e5; reviewed the diff against acceptance rather than re-implementing…
