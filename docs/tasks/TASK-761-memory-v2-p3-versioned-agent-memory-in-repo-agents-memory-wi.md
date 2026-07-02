---
id: TASK-761
title: "memory-v2 P3: versioned agent memory - in-repo .agents/memory with harness symlink repair + Trusted mirror"
swimlane: core
kind: feature
epic: memory-v2
labels: [memory, adapter, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-07-02
started: null
completed: null
agent_session: null
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
