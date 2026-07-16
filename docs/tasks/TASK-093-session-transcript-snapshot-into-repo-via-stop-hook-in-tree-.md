---
id: TASK-093
title: "Session transcript snapshot into repo via Stop hook (in-tree audit)"
swimlane: core
kind: feature
epic: null
labels: [hooks, session, transcript, audit, ready]
status: archive
priority: P2
appetite: "1d"
created: 2026-06-04
started: 2026-06-04
completed: 2026-06-04
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-093: Session transcript snapshot into repo via Stop hook (in-tree audit)

**Outcome (one sentence):** A Stop hook copies the live session transcript into .coding-os/<agent>/sessions/transcripts/<session-id>.jsonl so workflow sessions are auditable in-tree; the link to a task is the existing tasks.agent_session id.

## Read First
- src/core/hooks/registry.yaml
- src/core/hooks/agent-presence.sh
- src/adapters/claude/adapter.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a Stop event whose payload carries a `transcript_path`
- **When** snapshot-transcript.sh fires
- **Then** the transcript jsonl is atomically copied to `$COS_AGENT_DIR/sessions/transcripts/<session-id>.jsonl` (only when the source is newer — no redundant copy per turn), fail-open if `transcript_path` is absent.
- **Given** the meta-repo's own `.gitignore`
- **When** transcripts are written
- **Then** `.coding-os/**/transcripts/` is gitignored so chat content is never committed, and the hook is registered once in registry.yaml + rendered to both adapters.

## Work Log
- 2026-06-04 [claude]: Added snapshot-transcript.sh (Stop) — copies transcript_path to $COS_AGENT_DIR/sessions/transcripts/<sid>.jsonl, mtime-g
