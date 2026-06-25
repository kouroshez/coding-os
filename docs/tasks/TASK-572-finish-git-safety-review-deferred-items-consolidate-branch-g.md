---
id: TASK-572
title: "Finish git-safety review deferred items: consolidate branch_guard onto shared tokenizer (Phase C) + fail-closed test + nits"
swimlane: core
kind: refactor
epic: null
labels: [hooks, git-safety, review-findings, tech-debt, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-25
started: 2026-06-25
completed: 2026-06-25
agent_session: ses-claude-20260624-182639-f22b
depends_on: []
blocked_by: []
references: []
---
# TASK-572: Finish git-safety review deferred items: consolidate branch_guard onto shared tokenizer (Phase C) + fail-closed test + nits

**Outcome (one sentence):** Close the low/medium deferred findings from the TASK-566/567/571 adversarial review. (1) Phase C: delete branch_guard_check.py's ~94-line private tokenizer copy (_all_segments/_split_segments/_tokenize/_strip_env_vars/_strip_git_globals/_extract_backticks/_extract_nested_shells/_looks_like_env_assignment + 6 constants) and route _evaluate through the shared, now-;-aware-AND-quote-aware git_command_parse.command_groups — this both eliminates the two-divergent-tokenizers drift that caused the TASK-571 inconsistency AND fixes branch_guard's quote-blind false-positive (a commit message containing ';' + a git word currently false-blocks). (2) Add the missing fail-closed regression test (broken python3 on a git commit → block, exit 2) — a mutation flip to fail-open currently keeps the suite green. (3) Nits: name the magic recursion-depth literal (_MAX_NEST_DEPTH=8), strengthen branch_guard commit-a/symbolic-ref tests to assert the block REASON, and use the existing _cos_helpers_dir helper in block-secrets instead of the reinvented inline symlink dance.

## Read First
- src/core/hooks/_helpers/branch_guard_check.py
- src/core/hooks/_helpers/git_command_parse.py
- src/core/hooks/block-secrets.sh
- tests/test_branch_guard.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `git commit -m "refactor; git checkout other-branch is unsafe"` (a `;` + git word inside the quoted message) **When** branch-guard runs in trunk mode **Then** verdict=allow (no false block); but `true; git checkout -b foo` still blocks
- **Given** branch_guard_check.py after the refactor **When** grep for `_all_segments`/`_split_segments`/`_tokenize` private defs **Then** none remain (single shared tokenizer)
- **Given** a broken python3 on PATH and a `git commit --no-verify` **When** block-secrets.sh runs **Then** exit 2 (fail-closed), and a non-git command under the same broken helper → exit 0
- **Given** the full branch_guard + hooks + cli suites and the TASK-571 adversarial harness **When** run after the refactor **Then** all green (no separator/quote/force-push regression)
- **Then** make verify-hooks + golden regen stay clean

## Work Log
- 2026-06-25 [claude]: Edit branch_guard_check.py
- 2026-06-25 [claude]: Edit branch_guard_check.py
- 2026-06-25 [claude]: Edit branch_guard_check.py
- 2026-06-25 [claude]: Edit branch_guard_check.py
- 2026-06-25 [claude]: Edit verify_phasec.txt
- 2026-06-25 [claude]: Edit git_command_parse.py
- 2026-06-25 [claude]: Edit git_command_parse.py
- 2026-06-25 [claude]: Edit git_command_parse.py
- 2026-06-25 [claude]: Edit block-secrets.sh
- 2026-06-25 [claude]: Edit test_hooks.py
- 2026-06-25 [claude]: Edit test_branch_guard.py
- 2026-06-25 [claude]: Edit test_branch_guard.py
- 2026-06-25 [claude]: Phase C done: deleted branch_guard's ~94-line private tokenizer (8 functions + segmenter/backtick/nested-shell) and…
