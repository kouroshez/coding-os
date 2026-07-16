---
id: TASK-211
title: "enforce-commit-message.sh _helpers resolution broken in consumers \u2014 index.lock wait + commit-msg contract silently dead"
swimlane: core
kind: bug
epic: agent-hub
labels: [hooks, concurrency, consumer, index-lock, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-06
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260605-233300-41f3
depends_on: []
blocked_by: []
references: []
---
# TASK-211: enforce-commit-message.sh _helpers resolution broken in consumers — index.lock wait + commit-msg contract silently dead

**Outcome (one sentence):** enforce-commit-message.sh resolves `_helpers/` through the hook file's physical location (the `readlink` dance already used by branch-guard.sh:50-57), so `cos_wait_for_git_index_lock` (TASK-170/F4) AND the commit-message contract actually execute in consumer projects — today both silently no-op there because `.claude/hooks/*.sh` are individual symlinks and `.claude/hooks/_helpers/` is never created, while the meta-repo masks the bug via its `src/core/hooks/_helpers` fallback.

## Read First
- src/core/hooks/enforce-commit-message.sh
- src/core/hooks/branch-guard.sh (lines 48-57 — the proven physical-resolution dance)
- docs/engineering/agent-hub-orchestration.md (§4 F4 index.lock serialization)
- src/core/rules/git-workflow.md (Commit Message Contract)

## Repro Steps
1. In any consumer project scaffolded by `cos init` (where `.claude/hooks/enforce-commit-message.sh` is a symlink into the meta-repo and `.claude/hooks/_helpers/` does NOT exist), trigger the PreToolUse Bash hook by running a `git commit`.
2. Observe `_GIL` (line 22-23) resolves to `.claude/hooks/_helpers/git_index_lock.sh` (absent) then `$(git rev-parse --show-toplevel)/src/core/hooks/_helpers/...` (absent — consumer has no src/core tree); line 25's `[[ -f ]] && ... || true` silently no-ops, so the index.lock wait never runs.
3. Same broken resolution at lines 29-33 makes `extract_commit_msg_arg.py`/`check_commit_message.py` "missing → skipping; exit 0" — the commit-message contract is unenforced for the agent.

Expected: the helper resolves through the symlink target and both the index.lock wait and the message check run.
Actual: both silently skip in every consumer; only the meta-repo (which has src/core/) works.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a consumer-style install where the hook is invoked as a symlink (`.claude/hooks/enforce-commit-message.sh` → `src/core/hooks/enforce-commit-message.sh`) and no sibling `_helpers/` dir exists next to the symlink
- **When** the PreToolUse Bash hook fires on a `git commit`
- **Then** `_helpers/git_index_lock.sh`, `extract_commit_msg_arg.py`, and `check_commit_message.py` are all resolved via the physical (readlink-followed) hook directory, the index.lock wait runs, and a non-compliant commit message is still blocked (exit 2); meta-repo behavior is unchanged; `make verify-hooks` is green and a regression test asserts the helper resolves through a symlinked invocation.

## Work Log
- 2026-06-06 [claude]: Fixed: enforce-commit-message.sh now resolves _helpers/ via the readlink physical-location dance (mirrors branch-guard.s
- 2026-06-06 [claude]: committed 398d718e: src/core/hooks/enforce-commit-message.sh, tests/test_enforce_commit_message_symlink_resolution.py
