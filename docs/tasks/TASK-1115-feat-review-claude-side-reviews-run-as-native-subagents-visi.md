---
id: TASK-1115
title: "feat(review): Claude-side reviews run as native subagents, visible under the session in desktop and VS Code"
swimlane: "board_os"
kind: feature
epic: null
labels: [supervision, hooks, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-11-24
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1115: feat(review): Claude-side reviews run as native subagents, visible under the session in desktop and VS Code

**Outcome (one sentence):** When a review role runs on the session's own Claude adapter, the agent starts it as a native Claude Code subagent (cos-reviewer / cos-security-auditor) so the operator sees it under the session in Claude desktop and the VS Code plugin; a SubagentStart hook injects the review package and a SubagentStop hook writes the verdict to the review ledger, so the main agent never relays or alters it. Cross-provider reviews keep the detached dispatch and announce start and result in the chat.

## Read First
- docs/engineering/agent-supervision.md
- src/core/hooks/_helpers/auto_dispatch.py
- src/core/board_os/review_gate.py
- src/core/hooks/registry.yaml
- src/adapters/claude/adapter.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a Claude session and an unpinned or claude-pinned review, **When** the task enters testing, **Then** the hook writes the running rows and tells the agent, in BOARD_EVENTS context, to start Agent(subagent_type=cos-reviewer) with model sonnet for a routine review and no model (inherit) for a weighty one, and no detached SDK dispatch runs for that role.
- **Given** the cos-reviewer subagent starts, **When** SubagentStart fires, **Then** its context holds the task's review package: title, outcome, acceptance, review_scope diff, previous findings and verification evidence.
- **Given** the subagent finishes, **When** SubagentStop fires with last_assistant_message, **Then** the hook parses the ReviewerOutput JSON and records the done row, so the main agent's text never reaches the ledger.
- **Given** the agent never starts the subagent, **When** task-done runs, **Then** the gate's pending line tells it to start the subagent, and a stale row still ends as the ⚠️ warning.
- **Given** a codex-pinned review or a Codex session, **When** the task enters testing, **Then** the detached dispatch runs as today and the chat shows a start line naming role, adapter and model.
- **Given** the change, **When** the adapter templates and goldens are regenerated, **Then** the cos-reviewer and cos-security-auditor definitions reach consumer .claude/agents and the hook parity tests pass.

## Work Log
