---
id: TASK-761
title: "memory-v2 P3: versioned agent memory - in-repo .agents/memory with harness symlink repair + Trusted mirror"
swimlane: core
kind: feature
epic: memory-v2
labels: [memory, adapter, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-07-02
started: 2026-07-02
completed: 2026-07-02
agent_session: ses-claude-20260702-023419-c2e8
depends_on: [TASK-759]
blocked_by: []
references: []
---
# TASK-761: memory-v2 P3: versioned agent memory - in-repo .agents/memory with harness symlink repair + Trusted mirror

**Outcome (one sentence):** Agent memory lives in-repo (committed) at .agents/memory; the claude adapter symlinks the harness slug dir to it with SessionStart self-repair, renders Trusted lessons into MEMORY.md (<=200 lines, generated block, no clobber of manual notes), harvests foreign notes with content-hash dedup, and secret-scan covers the dir; Codex gets a read pointer per hook_capabilities.

## Read First
- docs/engineering/state-files.md
- docs/adapters/claude-sdk.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh clone on a blank machine, **When** the first session starts, **Then** the harness slug memory dir is a symlink into the repo and existing files were migrated without clobber
- **Given** new Trusted lessons, **When** the mirror renders, **Then** MEMORY.md generated block updates within the 200-line cap and manual notes outside the block survive
- **Given** a memory file containing a secret pattern, **When** a commit is attempted, **Then** the secret gate blocks it
- **Given** a lesson exported to the mirror, **When** the harvest runs, **Then** it is not re-imported (hash dedup + do-not-reimport marker)

## Work Log
- 2026-07-02 [claude]: Edit learning-extraction.md
- 2026-07-02 [claude]: Edit ensure-agent-memory-link.sh
- 2026-07-02 [claude]: Edit agent_memory_sync.py
- 2026-07-02 [claude]: Edit sync-agent-memory.sh
- 2026-07-02 [claude]: Edit _pre_commit_body.sh
- 2026-07-02 [claude]: Edit agent_memory_sync.py
- 2026-07-02 [claude]: Edit test_agent_memory_sync.py
- 2026-07-02 [claude]: Edit test_adapter_parity.py
- 2026-07-02 [claude]: Edit test_adapters.py
- 2026-07-02 [claude]: P3 complete (commit 099fef0f): ensure-agent-memory-link.sh (SessionStart, adapter_scope=claude, migrate-no-clobber,…
- 2026-07-02 [claude]: Status transitioned to complete via cos task-done.
