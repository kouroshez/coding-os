---
id: TASK-472
title: "Route cognition.py SDK option-construction through the builder + add P8 guard (P4-13)"
swimlane: infra
kind: refactor
epic: null
labels: [modularity, p8, audit-pass4, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-20
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-472: Route cognition.py SDK option-construction through the builder + add P8 guard (P4-13)

**Outcome (one sentence):** src/core/** no longer constructs ClaudeAgentOptions directly: cognition.py's inline sdk.ClaudeAgentOptions(...) sites (:1142, :1350) route through the existing importlib session-options builder seam (loaded at :570), and the anti-recurrence guard that session-options-builder.md:64 CLAIMS exists actually exists as a test. Restores the documented P8 invariant.

## Read First
- docs/adapters/session-options-builder.md
- src/core/web/routes/cognition.py
- src/adapters/claude/sdk_dispatcher.py
- docs/governance/critical-rules.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** src/core/web/routes/cognition.py importing claude_agent_sdk and building ClaudeAgentOptions inline at :1142/:1350 **When** the two construction sites are routed through the builder seam and an AST/grep guard test is added **Then** no ClaudeAgentOptions construction exists in src/core/** outside src/adapters/claude/sdk_dispatcher.py, the guard test fails if one is reintroduced, and tests/test_session_options_parity.py + server --test pass. (roles.py/presence.py probe imports + compress.py raw-anthropic are out of scope — note them separately.)

## Work Log
