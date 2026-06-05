---
id: TASK-153
title: "Codex Stop dispatcher must forward delegate stdout (decision:block + additionalContext) to wire the 3rd intent layer"
swimlane: core
kind: feature
epic: hook-remediation
labels: [codex, adapter, intent, audit-n6-followup]
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

# TASK-153: Codex Stop dispatcher must forward delegate stdout (decision:block + additionalContext) to wire the 3rd intent layer

**Outcome (one sentence):** codex-stop-dispatch.sh forwards/merges delegate exit-0 stdout — unwrap additionalContext via extract_additional_context.py (as the SessionStart dispatcher already does) and convert a {"decision":"block"} envelope into a Codex Stop block — so verify-completion-claim.sh + prevent-premature-done.sh become effective on Codex (today they are whitelisted Claude-only because their stdout is dropped). Needs a live `codex exec` run to verify Codex Stop honors additionalContext/block before removing them from CLAUDE_ONLY_WHITELIST.

## Read First
- src/adapters/codex/hooks/codex-stop-dispatch.sh
- src/adapters/codex/hooks/codex-sessionstart-dispatch.sh
- src/core/hooks/_helpers/extract_additional_context.py
- tests/test_adapter_parity.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
