---
id: TASK-418
title: "Consolidate hardcoded {claude,codex} adapter-id fallbacks into one data-driven SSOT (list_agent_ids)"
swimlane: "thinking_os"
kind: refactor
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-15
started: 2026-06-15
completed: 2026-06-15
agent_session: ses-claude-20260614-225343-4b14
depends_on: []
blocked_by: []
references: []
---
# TASK-418: Consolidate hardcoded {claude,codex} adapter-id fallbacks into one data-driven SSOT (list_agent_ids)

**Outcome (one sentence):** Adapter-id fallback literals live in exactly one core module; dispatcher/presence/roles derive known agents from a single list_agent_ids() that scans src/adapters — adding a new adapter (e.g. gemini) needs zero edits to these files.

## Read First
- src/core/thinking_os/dispatcher.py
- src/core/board_os/hub_adapter_manifest.py
- src/core/web/routes/presence.py
- src/core/web/routes/roles.py
- src/cli/adapter_registry.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a new adapter directory is added under src/adapters,
**When** the system resolves the set of known agent ids,
**Then** it is picked up with zero edits to dispatcher.py / presence.py / roles.py; and the literal {"claude","codex"} appears in at most one core module (the documented _BOARD_DEFAULTS fallback); and the thinking_os + board_os + web-route test suites stay green.

## Work Log
- 2026-06-15 [claude]: Edit hub_adapter_manifest.py
- 2026-06-15 [claude]: Edit dispatcher.py
- 2026-06-15 [claude]: Edit presence.py
- 2026-06-15 [claude]: Edit roles.py
- 2026-06-15 [claude]: Edit test_hub_adapter_manifest.py
- 2026-06-15 [claude]: Added list_agent_ids() SSOT in board_os/hub_adapter_manifest (scans src/adapters, fails soft to _BOARD_DEFAULTS). Rewire
- 2026-06-15 [claude]: committed 52ffe190: src/core/board_os/hub_adapter_manifest.py, src/core/thinking_os/dispatcher.py, src/core/web/routes/p
