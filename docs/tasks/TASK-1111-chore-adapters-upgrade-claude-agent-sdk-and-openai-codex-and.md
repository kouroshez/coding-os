---
id: TASK-1111
title: "chore(adapters): upgrade claude-agent-sdk and openai-codex, and run the newer installed claude CLI"
swimlane: adapters
kind: chore
epic: null
labels: [supervision, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-11-24
started: 2026-11-24
completed: 2026-11-24
agent_session: ses-claude-20261124-113611-864e
depends_on: []
blocked_by: []
references: []
---

# TASK-1111: chore(adapters): upgrade claude-agent-sdk and openai-codex, and run the newer installed claude CLI

**Outcome (one sentence):** Dispatch and Hub chat run on current SDKs: claude-agent-sdk 0.2.188 and openai-codex 0.172.0 with a matching lock. The Claude adapter runs the installed claude CLI when it is newer than the SDK's bundled copy, so a stale SDK no longer pins reviews to an old Claude Code.

## Read First
- src/adapters/claude/_claude_sdk_options.py
- src/adapters/codex/sdk_dispatcher.py
- pyproject.toml
- docs/adapters/claude-sdk.md

## Acceptance (G/W/T)
- **Given** the lock, **When** the cos environment is synced, **Then** claude-agent-sdk is 0.2.188 and openai-codex is 0.172.0.
- **Given** an installed claude CLI newer than the bundled one, **When** the Claude adapter dispatches or chats, **Then** it runs the installed CLI; an older or missing one falls back to the bundled CLI.
- **Given** the upgraded SDKs, **When** the adapter matrix suite runs, **Then** it passes.
- **Given** the upgraded SDKs, **When** a real reviewer dispatch runs on claude and on codex (CLI and python-sdk backends), **Then** each returns status ok with parsed output.

## Work Log
- 2026-11-24 [claude]: commit bff50e472a — chore(adapters): upgrade claude-agent-sdk to 0.2.188 and openai-codex to 0.172.0, run the newer CLI
- 2026-11-24 [claude]: commit 913dea6b3e — fix(adapters): the bundled codex runtime only upgrades an installed codex
- 2026-11-24 [claude]: commit 227dbb12e2 — fix(adapters): cache CLI version probes by mtime and accept only absolute claude paths
- 2026-11-24 [claude]: Live smoke: cos tool venv reinstalled with lock constraints (claude-agent-sdk 0.2.188, openai-codex 0.172.0, mcp…
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
