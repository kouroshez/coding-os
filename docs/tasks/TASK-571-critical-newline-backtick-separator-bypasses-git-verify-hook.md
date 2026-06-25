---
id: TASK-571
title: "CRITICAL: ;/newline/backtick separator bypasses git-verify-hook gate (regression in TASK-567 shared tokenizer) + force-push order + -mn FP"
swimlane: core
kind: bug
epic: null
labels: [hooks, git-safety, regression, review-findings, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-25
started: 2026-06-25
completed: 2026-06-25
agent_session: ses-claude-20260624-182639-f22b
depends_on: []
blocked_by: []
references: []
---
# TASK-571: CRITICAL: ;/newline/backtick separator bypasses git-verify-hook gate (regression in TASK-567 shared tokenizer) + force-push order + -mn FP

**Outcome (one sentence):** Close the critical separator-bypass regression the adversarial review found in the TASK-567 shared tokenizer (git_command_parse.command_groups), plus the high/medium siblings: a `;`/newline/backtick/brace-prefixed `git commit --no-verify` (or core.hooksPath/GIT_CONFIG_*) returns verdict=allow because `_punct_tokens` demoted `;` to whitespace (it is already in shlex's default punctuation_chars) so command_groups never splits and is_git_word(rest[0]) sees the leading non-git word. Also fix order-dependent force-push-to-main regexes (`git push origin main --force` and `+refs/heads/main` slip), the `-mn` commit-flag-cluster false-positive that over-blocks `git commit -mnope`, GIT_CONFIG_GLOBAL pointing at a non-/dev/null file, and the `git config --get core.hooksPath` read over-block. Add regression tests for every separator/grouping variant the suite missed.

## Read First
- src/core/hooks/_helpers/git_command_parse.py
- src/core/hooks/_helpers/check_git_bypass.py
- src/core/hooks/block-dangerous-commands.sh
- tests/test_hooks.py

## Repro Steps
From the git-safety-review workflow (34 agents, 29 confirmed). REPRODUCED locally: a `true;`-prefixed git commit --no-verify returns verdict=allow (BYPASS) while plain and `&&`-prefixed both block. Backtick-wrapped commit also allows. Root cause: git_command_parse.py `_punct_tokens` does `lex.whitespace = lex.whitespace + ";"`; default punctuation_chars is already `();<>|&` (includes `;`), so the hack swallows `;` as whitespace and command_groups returns one merged group whose first word is non-git, so git_invocations()==[]. Force-push: trailing --force and +refs/heads/main both slip block-dangerous regexes. -mn: commit_flags('-mn x') returns {m,n} so check_git_bypass false-blocks legit attached-message commits.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `true; git commit --no-verify` (and the newline, backtick, and `{ ...; }` brace variants) **When** check_git_bypass.py runs **Then** verdict=block (parity with the `&&` form)
- **Given** a commit message containing `;` and parens **When** the tokenizer runs **Then** the message stays one token and the commit is NOT false-blocked
- **Given** a force-push to main with the flag AFTER the refspec, and a `+refs/heads/main` refspec **When** block-dangerous-commands.sh runs **Then** both rc=2 (blocked regardless of flag order/qualification)
- **Given** `git commit -mnope` (attached -m message, no real -n) **When** check_git_bypass.py runs **Then** verdict=allow; but `-nm x` / `-n` still block
- **Given** `git config --get core.hooksPath` (a READ) **When** check_git_bypass.py runs **Then** verdict=allow; a config WRITE still blocks
- **Then** make verify-hooks + test_hooks + test_branch_guard + golden regen all green with explicit separator/grouping regression tests

## Work Log
- 2026-06-25 [claude]: Edit git_command_parse.py
- 2026-06-25 [claude]: Edit git_command_parse.py
- 2026-06-25 [claude]: Edit git_command_parse.py
- 2026-06-25 [claude]: Edit git_command_parse.py
- 2026-06-25 [claude]: Edit check_git_bypass.py
- 2026-06-25 [claude]: Edit check_git_bypass.py
- 2026-06-25 [claude]: Edit block-dangerous-commands.sh
- 2026-06-25 [claude]: Edit verify_571.txt
- 2026-06-25 [claude]: Edit test_hooks.py
- 2026-06-25 [claude]: Edit test_hooks.py
- 2026-06-25 [claude]: Edit test_hooks.py
- 2026-06-25 [claude]: Edit test_branch_guard.py
- 2026-06-25 [claude]: Fixed the critical regression + siblings. Root cause: git_command_parse._punct_tokens added `;` to lex.whitespace,…
