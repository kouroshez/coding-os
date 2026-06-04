---
id: TASK-090
title: "Session transcript snapshot hook + commit↔task linking + real per-panel attribution"
swimlane: infra
kind: feature
epic: null
labels: [board, hooks, session, transcript, attribution, ready]
status: icebox
priority: P2
appetite: "1d"
created: 2026-06-04
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-090: Session transcript snapshot hook + commit↔task linking + real per-panel attribution

**Outcome (one sentence):** Each workflow session's chat transcript is snapshotted into .coding-os/<agent>/sessions/transcripts/ and linked to its task; commits referencing a task append to its work log; tasks are attributed to the real per-panel session id.

## Read First
- src/core/hooks/registry.yaml
- src/core/hooks/capture-work-log.sh
- src/core/web/routes/presence.py
- docs/engineering/state-files.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a workflow session ends (Stop / SessionEnd) with a `transcript_path` in the hook payload
- **When** the new snapshot hook fires
- **Then** the transcript jsonl is atomically copied to `.coding-os/<agent>/sessions/transcripts/<session-id>.jsonl` and the active task records the link — global `~/.claude` sessions of non-workflow repos are untouched.
- **Given** a `git commit` lands referencing TASK-NNN (or with an active `.task-current`)
- **When** the post-commit capture runs
- **Then** the commit sha + subject is appended to that task's Work Log.
- **Given** a task is created/started by a panel
- **When** attribution is stamped
- **Then** `agent_session` is the real per-panel `ses-<agent>-…` id, not a PPID fallback.

## Notes
Approach (3 parts, each its own commit):
1. **Transcript snapshot** — new `snapshot-transcript.sh` (Stop + SessionEnd), reads `.transcript_path` from stdin, atomic `cp` to `$COS_AGENT_DIR/sessions/transcripts/`. Register in `registry.yaml`, `make regen-adapter-templates`, dogfood install, regenerate `tests/golden/**` (per-section capture to avoid the concurrent-agent golden collision). Codex parity bounded by SessionEnd matcher capability in `adapters/codex/adapter.yaml::hook_capabilities`. Transcript-storage redirect is officially unsupported by Claude Code (snapshot is the only path). Add `.coding-os/**/transcripts/` to `.gitignore`.
2. **Commit↔task link** — extend `capture-work-log.sh` (or a small PostToolUse Bash matcher) to detect a successful `git commit`, parse TASK-NNN from the message or read `.task-current`, and `cos_work_log_append` the sha + subject. No new registration if folded into an existing Bash-matcher hook.
3. **Real attribution** — the long-lived MCP server can't see the calling panel; have hook-driven `cos task-*` calls pass the panel `session-id`, and/or thread a session arg through the MCP tool wrappers so `_resolve_attribution` stops falling back to PPID.

## Work Log
