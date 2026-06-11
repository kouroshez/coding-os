---
id: TASK-021
title: "add /compose slash command + nudge upgrade for role-chain dispatch"
swimlane: core
kind: feature
epic: null
labels: [cognition, roles, ux]
status: complete
priority: P1
appetite: "1h"
created: 2026-05-23
started: 2026-05-23
completed: 2026-05-23
agent_session: ses-claude-20260523-010526-e647
depends_on: []
blocked_by: []
references:
  - src/core/commands/classify.md
  - src/core/hooks/nudge-thinking-os.sh
  - src/core/thinking_os/agents/README.md
---
# TASK-021: /compose slash command + nudge upgrade

**Outcome (one sentence):** Agents land on `/compose` (one keystroke) instead of having to recall the verbose `cos_compose_chain(task_id=…)` shape — first concrete step toward closing the dead-path captured in audit-roles-dead.md (formula_dispatches=2 lifetime).

This is the user-facing surface layer. Programmatic auto-trigger (hook calling formula_composer directly when `.thinking_os-gate` records COMPLICATED+) is intentionally deferred to Phase 9 — it needs an audited bridge from a Bash hook into the in-process Python composer, plus a `.formula-chain.json` contract that session-context.sh can render in additionalContext. Out of scope here.

## Read First
- [src/core/commands/classify.md](../../src/core/commands/classify.md) — pattern for thin slash commands that hand off to MCP tools
- [src/core/hooks/nudge-thinking-os.sh](../../src/core/hooks/nudge-thinking-os.sh) — the UserPromptSubmit hook whose `additionalContext` currently lists `cos_compose_chain` verbatim
- [src/core/thinking_os/agents/README.md](../../src/core/thinking_os/agents/README.md) — 11-role catalog the composer dispatches into

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a session classified COMPLICATED+ in the thinking_os gate
- **When** the agent types `/compose` (or sees the nudge upgrade)
- **Then** the slash command resolves to a call into `cos_compose_chain` with the active task's signals, and the agent receives the composed role chain in the same response; the nudge text in `nudge-thinking-os.sh` is updated to point at `/compose` instead of the bare tool name; `make verify-hooks` clean; `make docs-lint` clean.

## Work Log
- 2026-05-23 — added [src/core/commands/compose.md](../../src/core/commands/compose.md) (5-step slash command wrapping `cos_compose_chain`), upgraded the [nudge-thinking-os.sh](../../src/core/hooks/nudge-thinking-os.sh) line 105 nudge text to point at `/compose` instead of the bare `cos_compose_chain` tool name, and authored the roles-dead forensic note (since retired) with the corrected fix path. `make verify-hooks` clean, `make docs-lint` clean. Deeper auto-trigger (Bash hook → formula_composer in-process + session-context.sh integration) deferred to Phase 9.
- 2026-05-23 [claude]: Status transitioned to complete via cos task-done.
