---
id: TASK-1024
title: "governance: block turn-end on unaudited prose \u2014 mandatory humanizer second pass"
swimlane: core
kind: feature
epic: null
labels: [governance, skills, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-24
started: 2026-08-24
completed: 2026-08-24
agent_session: ses-claude-20260820-192937-ef87
depends_on: []
blocked_by: []
references: []
---
# TASK-1024: governance: block turn-end on unaudited prose — mandatory humanizer second pass

**Outcome (one sentence):** A session that drafted prose cannot end until the agent has re-run the humanizer patterns over the text it produced and recorded the result, closing the gap where loading the skill was mistaken for applying it.

## Read First
- src/core/hooks/nudge-humanizer.sh
- src/core/hooks/check-capture-worked.sh
- src/core/skills/humanizer/SKILL.md
- src/core/hooks/registry.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a session where nudge-humanizer fired and no audit receipt was written
  **When** the turn tries to end
  **Then** the Stop hook exits 2 and names the exact second-pass command.
- **Given** the same session after `write-state.sh .humanizer-audit "reviewed:<n>"`
  **When** the turn tries to end
  **Then** the hook exits 0.
- **Given** a Stop payload carrying `stop_hook_active: true`
  **When** the hook runs
  **Then** it exits 0 without blocking, so a failed audit can never trap the session in a loop.
- **Given** a session where no prose intent was ever detected
  **When** the turn ends
  **Then** the hook exits 0 and injects nothing.

## Work Log
- 2026-08-24 [claude]: Edit enforce-humanizer-audit.sh
- 2026-08-24 [claude]: Edit enforce-humanizer-audit.sh
- 2026-08-24 [claude]: Edit registry.yaml
- 2026-08-24 [claude]: Edit SKILL.md
- 2026-08-24 [claude]: Edit codex-stop-dispatch.sh
- 2026-08-24 [claude]: Edit enforce-humanizer-audit.sh
- 2026-08-24 [claude]: commit b1a6c5ae8c — feat(hooks): block turn-end on prose drafted without a humanizer audit pass
- 2026-08-24 [claude]: Status transitioned to complete via cos task-done.
