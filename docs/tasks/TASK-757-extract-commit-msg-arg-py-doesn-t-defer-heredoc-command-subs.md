---
id: TASK-757
title: "extract_commit_msg_arg.py doesn't defer heredoc/command-substitution commit messages \u2014 mis-validates them instead"
swimlane: core
kind: bug
epic: null
labels: [hooks, git-workflow, ready]
status: complete
priority: P2
appetite: 1h
created: 2026-07-01
started: 2026-07-01
completed: 2026-07-01
agent_session: ses-claude-20260701-140116-619f
depends_on: []
blocked_by: []
references: []
---
# TASK-757: extract_commit_msg_arg.py doesn't defer heredoc/command-substitution commit messages — mis-validates them instead

**Outcome (one sentence):** A `git commit -m "$(cat <<EOF ... EOF)"` invocation with a well-formed Conventional Commit message is either validated correctly against its real title/body split, or cleanly deferred to the git-level commit-msg hook as the module docstring already promises — it must never be blocked on a garbled multi-hundred-character pseudo-title.

## Read First
- src/core/hooks/_helpers/extract_commit_msg_arg.py
- src/core/hooks/_helpers/git_command_parse.py
- src/core/hooks/enforce-commit-message.sh
- src/core/hooks/_helpers/check_commit_message.py

## Repro Steps
Ran `git commit -m "$(cat <<'EOF'\ntitle line\n\nbody line\nEOF\n)" -- somefile` (a normal heredoc-substitution commit, well-formed after shell expansion) inside this session. enforce-commit-message.sh BLOCKed it: "title is 412 chars; max 100" / "title is not a Conventional Commit". Root cause traced to extract_commit_msg_arg.py's shlex-based tokenizer: it does NOT skip command-substitution/heredoc `-m` values as its own docstring claims ("Forms the tokenizer can't cleanly resolve (heredoc -F-, command substitution) yield no message and defer") — instead it captures the raw unexpanded `$(cat <<'EOF' ... )` text (heredoc markers included, newlines collapsed to `; `) as if it were the literal commit message, and check_commit_message.py then validates that garbage as the title. Verified directly: piping the exact command string through extract_commit_msg_arg.py returns the literal `$(cat <<'EOF'; ...; EOF; )` blob, not empty.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a `git commit -m "$(cat <<'EOF' ... )"` command string, **When** extract_commit_msg_arg.py parses it, **Then** it returns empty (defers to the git-level commit-msg hook) rather than a garbled command-substitution blob — matching its own documented contract.
- **Given** a plain `git commit -m "title" -m "body"` (the documented multi-`-m` paragraph form), **When** extract_commit_msg_arg.py parses it, **Then** behavior is unchanged (no regression) — covered by existing check_commit_message.py / hook tests.
- **Given** the fix, **When** `make verify-hooks` runs, **Then** it passes.

## Work Log
- 2026-07-01 [claude]: Edit extract_commit_msg_arg.py
- 2026-07-01 [claude]: Edit test_extract_commit_msg_arg.py
- 2026-07-01 [claude]: committed 7c573f13 · 2 files
- 2026-07-01 [claude]: Root cause: git_command_parse.normalize() collapses every raw newline to "; " before tokenizing (correct for real…
