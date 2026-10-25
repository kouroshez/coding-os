---
id: TASK-1074
title: "Delete the DB-backed agent memory: tools, hooks, code, Hub page and tables"
swimlane: infra
kind: refactor
epic: null
labels: [ready, governance, docs-update]
status: in_progress
priority: P1
appetite: 1d
created: 2026-10-24
started: 2026-10-24
completed: null
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1074: Delete the DB-backed agent memory: tools, hooks, code, Hub page and tables

**Outcome (one sentence):** The observation/learned-pattern memory stack is gone from coding-os and every consumer: no cos_search/cos_learn_*/cos_details/cos_timeline/cos_observation_record/cos_retrieval_*/cos_promote/cos_digest_regenerate tools, no capture/decay/digest/recall hooks, no Hub Memory page, and graph, docs, tasks and cognition keep working.

## Read First
- src/core/subsystems.yaml
- src/core/rules/memory.md
- docs/governance/mcp-tool-inventory.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the MCP server starts, **When** its tools are listed, **Then** none of the memory-module tools are registered and server.py --test passes.
- **Given** a session starts and ends in a consumer, **When** the hooks run, **Then** no hook writes observations, decays patterns or emits an Agent Digest, and no hook errors.
- **Given** the Hub, **When** I open any page, **Then** there is no Memory page or memory widget and the UI build and tests pass.
- **Given** the graph_os, board_os and thinking_os suites, **When** they run, **Then** they pass.

## Work Log
- 2026-10-24 [claude]: Plan: delete the memory module's 15 tools, 7 hooks, capture/decay/digest/distill/session-enrich/learning code, the…
- 2026-10-25 [claude]: Resumed after the crash fix. Cleared the last live refs (auto-compose recall + CLEAR pass-through,…
