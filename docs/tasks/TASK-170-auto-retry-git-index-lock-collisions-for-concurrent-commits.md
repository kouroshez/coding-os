---
id: TASK-170
title: "Auto-retry git index.lock collisions for concurrent commits"
swimlane: core
kind: feature
epic: agent-hub
labels: [ready]
status: archive
priority: P2
appetite: "4h"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260605-183120-db30
depends_on: []
blocked_by: []
references: []
---
# TASK-170: Auto-retry git index.lock collisions for concurrent commits

**Outcome (one sentence):** Concurrent commits racing `.git/index.lock` no longer fail hard — a pre-emptive bounded wait (with verified-stale recovery, never a blind delete) serializes them transparently, wired into the existing PreToolUse `git commit` gate.

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/core/hooks/enforce-commit-message.sh
- src/core/rules/git-workflow.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a `.git/index.lock` held by a concurrent commit
- **When** the agent's `git commit` PreToolUse gate runs
- **Then** it waits (bounded ~10s) for the lock to clear before allowing the command; a verified-stale lock (mtime older than a normal commit could take) is removed exactly once; no lock blindly deleted; fail-open so it never blocks the command. Isolated bash test covers no-lock / stale-lock / fresh-lock-clears; shellcheck + `make verify-hooks` green.

## Work Log
- 2026-06-05 [claude]: Added cos_wait_for_git_index_lock helper (bounded pre-emptive wait + verified-stale reap, portable stat -f/-c) wired int
