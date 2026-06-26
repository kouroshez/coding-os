---
id: TASK-587
title: "Harden agent-side git guards: indirection-bypass backstop + hub-settings Bash-write guard + pr-mode update-ref HEAD"
swimlane: core
kind: security
epic: git-foundation-hardening
labels: [git, pr-mode, defense-in-depth, bypass, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-26
started: 2026-06-26
completed: 2026-06-26
agent_session: ses-claude-20260625-235014-c028
depends_on: []
blocked_by: []
references: []
---
# TASK-587: Harden agent-side git guards: indirection-bypass backstop + hub-settings Bash-write guard + pr-mode update-ref HEAD

**Outcome (one sentence):** Close 3 verified client-side guard holes (defense-in-depth; server-side branch protection stays the authoritative wall): (1) shell-indirection bypass — eval/pipe-to-sh/here-string/xargs hides the git word from the static parser; (2) hub-settings.json is Bash-writable so a pr-mode agent can self-downgrade to trunk then push to main; (3) pr-mode allows `git update-ref HEAD <sha>`/`-d HEAD`, a HEAD-rewrite on the shared checkout that trunk blocks.

## Read First
- docs/playbooks/pr-workflow.md
- src/core/hooks/_helpers/branch_guard_check.py
- src/core/hooks/block-dangerous-commands.sh
- src/core/hooks/_helpers/git_command_parse.py
- src/core/hooks/cos-env.sh

## Threat Model
Adversary = a misaligned or prompt-injected agent (the client runtime is untrusted; client-side hooks are fast-feedback, NOT the security boundary — server-side branch protection is). Assets protected = the integration/protected branch (no unreviewed/un-CI'd code reaches it) and the pr-mode policy file itself (hub-settings.json). Attack surface, each verified by running the real parser: (a) `eval '…'`, `printf '…'|sh`, `sh <<< '…'`, `xargs git …` strip the git word from the static tokenizer, so every git PreToolUse guard ALLOWs a protected-branch push or no-verify commit; (b) the file guards match only Write|Edit, so a Bash redirect / `tee` / `python -c` write to hub-settings.json flips pr→trunk where a non-force push to main is legal; (c) pr-mode's `_pr_check` update-ref branch never re-applies trunk's HEAD guard, so `git update-ref HEAD <sha>` rewrites the shared HEAD. Mitigation (no shell interpreter, no arms race): coarse fail-closed backstops — block (git-verb + indirection-construct) in pr-mode and force-push-main in trunk; extend the Bash leg to refuse writes resolving under a `.coding-os/` policy file (+ cos-env fail-closed-to-pr on an unparseable-after-enabled file); add the 3-line update-ref HEAD parity guard. Residual risk on a properly-protected GitHub remote is bounded by Layer-0 (the server rejects the push regardless of any client bypass); the holes fully bite only on an unprotected remote (legibility tracked by TASK-586).

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** pr-mode active, **When** the agent runs `eval 'git push origin main'`, `printf 'git push origin main'|sh`, `sh <<< 'git push origin main'`, or `echo main|xargs git push origin`, **Then** branch-guard BLOCKs (exit 2). **Given** trunk mode, **When** `eval 'git push --force origin main'` runs, **Then** block-dangerous-commands BLOCKs. **Given** any Bash write/redirect/tee/`python -c` whose target resolves under a `.coding-os/` policy file (hub-settings.json), **When** the PreToolUse Bash hook fires, **Then** it is BLOCKed. **Given** pr-mode and not worktree-scoped, **When** `git update-ref HEAD <sha>` or `git update-ref -d HEAD` runs, **Then** BLOCK pr-shared-head-rewrite (worktree-scoped stays allowed). **Given** a legitimate non-git `eval`/`xargs`/redirect, **When** it runs, **Then** it is NOT blocked (no false positive). Verify: make verify-hooks green AND the branch-guard/dangerous-commands/secrets hook unit tests green.

## Work Log
- 2026-06-26 [claude]: Edit pr-workflow.md
- 2026-06-26 [claude]: Edit pr-workflow.md
- 2026-06-26 [claude]: Edit git_command_parse.py
- 2026-06-26 [claude]: Edit check_recover.py
- 2026-06-26 [claude]: Edit branch_guard_check.py
- 2026-06-26 [claude]: Edit branch_guard_check.py
- 2026-06-26 [claude]: Edit branch_guard_check.py
- 2026-06-26 [claude]: Edit check_bguard.py
- 2026-06-26 [claude]: Edit recover_indirect.py
- 2026-06-26 [claude]: Edit check_settings_write.py
- 2026-06-26 [claude]: Edit check_settings.py
- 2026-06-26 [claude]: Edit block-dangerous-commands.sh
- 2026-06-26 [claude]: Edit block-dangerous-commands.sh
- 2026-06-26 [claude]: Edit block-dangerous-commands.sh
- 2026-06-26 [claude]: Edit block-dangerous-commands.sh
- 2026-06-26 [claude]: Edit block-dangerous-commands.sh
- 2026-06-26 [claude]: Edit block-dangerous-commands.sh
- 2026-06-26 [claude]: Edit block-dangerous-commands.sh
- 2026-06-26 [claude]: Edit block-dangerous-commands.sh
- 2026-06-26 [claude]: Edit check_blockdang.py
- 2026-06-26 [claude]: Edit cos-env.sh
- 2026-06-26 [claude]: Edit check_cosenv.sh
- 2026-06-26 [claude]: Edit test_branch_guard.py
- 2026-06-26 [claude]: Edit test_block_dangerous_commands.py
- 2026-06-26 [claude]: commit 236f8ce912 — fix(hooks): close indirection, settings-write & pr-mode update-ref HEAD git-guard bypasses
- 2026-06-26 [claude]: Closed 3 client-side guard holes (defense-in-depth; server branch protection stays the wall). 587a:…
