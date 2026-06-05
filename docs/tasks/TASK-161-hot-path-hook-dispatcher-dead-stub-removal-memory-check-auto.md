---
id: TASK-161
title: "Hot-path hook dispatcher + dead-stub removal + memory-check auto-stamp (golden-heavy, needs clean window)"
swimlane: core
kind: feature
epic: hook-remediation
labels: [hooks, registry, golden, performance, audit-n9-followup]
status: icebox
priority: P2
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-161: Hot-path hook dispatcher + dead-stub removal + memory-check auto-stamp (golden-heavy, needs clean window)

**Outcome (one sentence):** Three registry+golden-touching changes done together in a clean window (no concurrent hook/UI session): (9a) single PreToolUse + single PostToolUse Write|Edit in-process dispatcher that parses stdin once and fans out to the ~23 gate hooks, cutting ~42 subprocess spawns per edit — with a per-gate regression test proving every block still fires; (9b) delete the dead no-op stubs verify-changed-file.sh + doc-sync-reminder.sh and their registry entries + scaffold_manifest + test-hooks + 2 test files + re-capture all tests/golden snapshots; (5d) a PostToolUse hook matched on the cos_search/cos_learn_suggest MCP tool that authentically stamps .memory-check (replacing the self-attested marker). All three require regen-adapter-templates + a full golden re-capture across every stack×adapter, so they must NOT run concurrently with another hooks/golden session (collision) — hence deferred from the N9 audit tail.

## Read First
- src/core/hooks/registry.yaml
- src/adapters/codex/hooks/codex-pretool-dispatch.sh
- src/cli/hook_renderer.py
- src/core/hooks/test-hooks.sh
- tests/test_adapter_parity.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
