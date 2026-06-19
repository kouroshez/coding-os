---
id: TASK-449
title: "B-2 fix: hardcoded-literals safety hook silently inert on every consumer (CHECKER path bug)"
swimlane: core
kind: bug
epic: null
labels: [modularity-audit-pass3, safety-hook, F12, ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-06-19
started: 2026-06-19
completed: null
agent_session: ses-claude-20260619-063923-1c50
depends_on: []
blocked_by: []
references: []
---
# TASK-449: B-2 fix: hardcoded-literals safety hook silently inert on every consumer (CHECKER path bug)

**Outcome (one sentence):** block-hardcoded-literals.sh resolves its checker against the REAL src/core/hooks dir via cos-env's _cos_helpers_dir symlink resolver, so the PreToolUse SSOT-drift gate actually fires. Before: invoked via the .claude/hooks/ dir-of-symlinks, $(dirname $0)/../scripts resolved to the nonexistent .claude/scripts/ so `[[ ! -f CHECKER ]] && exit 0` made the safety hook silently pass a hardcoded 'django' in cli/*.py on every consumer AND the meta-repo dogfood itself. Also: missing-checker is now a loud stderr WARN (never silent), and the rc=2 block path no longer dies under set -e so the override hint prints.

## Read First
- src/core/hooks/block-hardcoded-literals.sh
- src/core/hooks/cos-env.sh
- docs/engineering/modularity-audit-2026-06.md

## Repro Steps
printf '{"tool_name":"Write","tool_input":{"file_path":"src/cli/foo.py","content":"BACKEND = \"django\""}}' | bash .claude/hooks/block-hardcoded-literals.sh ; echo $?  — pre-fix prints 0 (silent pass), post-fix prints 2 (BLOCK).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a Write of `BACKEND = "django"` to src/cli/foo.py invoked through .claude/hooks/block-hardcoded-literals.sh **When** the hook runs **Then** it exits 2 (BLOCK) and names the literal.
- **Given** clean cli content with no stack/adapter literal **When** the hook runs **Then** it exits 0 (allow).
- **Given** a non-cli path (src/backend/x.py) **When** the hook runs **Then** it exits 0 (out of scope).
- **Given** make verify-hooks **When** run **Then** syntax + shellcheck are clean.

## Work Log
