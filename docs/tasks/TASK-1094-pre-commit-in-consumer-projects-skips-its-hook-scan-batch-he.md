---
id: TASK-1094
title: "pre-commit in consumer projects skips its hook scan: batch helper not found"
swimlane: core
kind: bug
epic: null
labels: [hooks, consumer, ready]
status: in_progress
priority: P2
appetite: 1d
created: 2026-11-23
started: 2026-11-26
completed: null
agent_session: ses-claude-20261126-141006-a0f1
depends_on: []
blocked_by: []
references: []
---
# TASK-1094: pre-commit in consumer projects skips its hook scan: batch helper not found

**Outcome (one sentence):** In a cos init consumer project, the git pre-commit hook finds pre_commit_batch.py and runs its scan instead of warning and skipping.

## Read First
- (no doc yet — exploratory)

## Repro Steps
1. In a consumer project (e.g. /Users/ciro/Files/Project/Streaming-Channels, coding-os 0.4.1 + ab368d81), stage any file and `git commit`.
2. Output: `cos pre-commit: WARNING — batch helper missing; skipping hook scan. expected at: <repo>/src/core/hooks/_helpers/pre_commit_batch.py`.
3. Cause: `.git/hooks/pre-commit` calls `command -v _cos_helpers_dir` after sourcing `.claude/hooks/cos-env.sh`, but that function now lives in the leaf `src/core/hooks/_cos_env_paths.sh:105` and is not defined after sourcing cos-env.sh (checked). `.claude/hooks/_helpers` is not linked in consumers, and the last fallback `src/core/hooks/_helpers` only exists in the meta-repo.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh consumer project from `cos init`
- **When** a file is staged and committed
- **Then** pre-commit resolves the helpers dir, runs pre_commit_batch.py, and prints no "batch helper missing" warning; a test covers the consumer path

## Work Log
- 2026-11-26 [claude]: Reproduced in a fresh claude,codex fastapi scaffold: `bash .git/hooks/pre-commit` prints "batch helper missing;…
- 2026-11-26 [claude]: Reproduced in a fresh claude,codex fastapi scaffold: `bash .git/hooks/pre-commit` prints "batch helper missing;…
