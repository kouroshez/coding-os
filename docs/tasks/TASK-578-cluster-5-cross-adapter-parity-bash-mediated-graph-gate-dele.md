---
id: TASK-578
title: "Cluster 5 \u2014 Cross-adapter parity: Bash-mediated graph-gate delegate for Codex + dispatcher graph preamble + rename completeness block path"
swimlane: core
kind: feature
epic: graph-first-enforcement
labels: [multi-adapter, codex, parity, dispatcher, graph-gate, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-25
started: null
completed: null
agent_session: null
depends_on: [TASK-573, TASK-577]
blocked_by: []
references: []
---

# TASK-578: Cluster 5 — Cross-adapter parity: Bash-mediated graph-gate delegate for Codex + dispatcher graph preamble + rename completeness block path

**Outcome (one sentence):** Codex (Bash-only) gets graph-first parity: a Bash PreToolUse delegate parses the target path out of apply_patch/sed/tee and runs the same graph-gate logic; hook_renderer.py turns the silent `if rendered_matcher is None: continue` into a tracked parity-deficit report so a dropped enforce gate is visible not silent; the cross-adapter dispatcher forwards allowed_tools and prepends a non-optional 'cos_graph_context before any Edit' preamble, and cos_supervise_record_output verifies the .graph/ marker for each load-bearing path the sub-agent touched; verify-rename-callers gains a real block path (records an escalation marker rather than always exit 0). Closes N1, N2, N11.

## Read First
- src/adapters/codex/adapter.yaml
- src/cli/hook_renderer.py
- src/adapters/codex/sdk_dispatcher.py
- src/core/thinking_os/dispatcher.py
- src/core/hooks/verify-rename-callers.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a Codex session editing a load-bearing file via apply_patch **When** the Bash delegate runs **Then** the same graph-gate enforcement applies (warn/block per mode) instead of silent absence; **Given** the renderer drops a Write/Edit hook for a Bash-only adapter **When** rendering completes **Then** a parity-deficit report records it; **Given** a cross-adapter dispatch **When** the sub-agent edits **Then** the graph preamble is injected and the marker is verified post-hoc; AND adapters + adapter_parity + verify-hooks matrix suites green.

## Work Log
