---
id: TASK-950
title: "Adapter chat/dispatch availability is probed per capability, never a hardcoded runtime string"
swimlane: adapters
kind: feature
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-12
started: 2026-08-12
completed: 2026-08-12
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-950: Adapter chat/dispatch availability is probed per capability, never a hardcoded runtime string

**Outcome (one sentence):** The Hub reports chat and dispatch availability per adapter by probing its runtime entrypoints and discovering its models, so an adapter that works is offered and one that does not states the reason and the remedy instead of a permanent "coming soon".

## Read First
- src/core/web/routes/_config_read.py
- src/adapters/codex/adapter.yaml
- src/adapters/codex/chat_provider.py
- src/core/web/ui/src/features/cognition/ModelPicker.tsx
- docs/engineering/adapter-parity.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the codex adapter whose dispatcher resolves a real CLI binary and whose chat SDK is installed
**When** a client requests /api/config/adapters and opens the Hub chat model picker
**Then** codex reports chat and dispatch availability independently from probes rather than from runtime=="in_process", exposes the model discovered from the user's own codex config instead of an empty list, and any unavailable capability carries a concrete reason and remedy string that names the missing dependency.

## Work Log
- 2026-08-12 [claude]: Edit chat_provider.py
- 2026-08-12 [claude]: Edit _config_adapters.py
- 2026-08-12 [claude]: Edit _config_read.py
- 2026-08-12 [claude]: Edit SKILL.md
- 2026-08-12 [claude]: Edit _config_read.py
- 2026-08-12 [claude]: Edit _config_read.py
- 2026-08-12 [claude]: Edit SKILL.md
- 2026-08-12 [claude]: Edit _config_adapters.py
- 2026-08-12 [claude]: Edit _config_read.py
- 2026-08-12 [claude]: Edit _config_read.py
- 2026-08-12 [claude]: Edit _config_read.py
- 2026-08-12 [claude]: Edit ModelPicker.tsx
- 2026-08-12 [claude]: Edit ModelPicker.tsx
- 2026-08-12 [claude]: Edit ModelPicker.tsx
- 2026-08-12 [claude]: Edit ModelPicker.tsx
- 2026-08-12 [claude]: Status transitioned to complete via cos task-done.
- 2026-08-12 [claude]: Status transitioned to complete via cos task-done.
