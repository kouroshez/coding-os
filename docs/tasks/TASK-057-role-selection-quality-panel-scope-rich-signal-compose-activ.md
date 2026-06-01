---
id: TASK-057
title: "Role selection quality + panel-scope: rich-signal compose, active-role phase switch, .roles panel-scoped"
swimlane: thinking_os
kind: bug
epic: null
labels: []
status: complete
priority: P1
appetite: "1d"
created: 2026-06-01
started: 2026-06-01
completed: 2026-06-01
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-057: Role selection quality + panel-scope: rich-signal compose, active-role phase switch, .roles panel-scoped

**Outcome (one sentence):** Roles compose from real prompt signals (not always analyst), the active role advances with work phase, and .roles/.role are panel-scoped per TASK-035 so concurrent panels never collide.

## Read First
- docs/tasks/audits/audit-roles-selection-panelscope.md
- docs/tasks/audits/audit-cognition-autotrigger.md
- src/core/thinking_os/formula_composer.py

## Repro Steps
1. Start any session, record a COMPLICATED/COMPLEX gate, submit any prompt.
2. Observe the banner `roles=` field across multiple different prompts.
Expected: chain varies by task (debug→debugger, audit→security_auditor, …); active role advances as work moves analyze→implement→verify.
Actual (before fix): every prompt → `roles=analyst`, frozen for the whole session — composer was fed only complexity+dims so only `analyst` cleared min_score; banner always showed `chain[0]`.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a COMPLICATED/COMPLEX gate, **When** auto-compose-roles fires with the prompt, **Then** the chain reflects prompt action/domain (debug→debugger, audit→security_auditor, refactor→refactorer) instead of always `['analyst']`.
- **Given** a composed chain, **When** the agent does a Write/Edit then a test/verify Bash command, **Then** `.role` advances (implementer→reviewer) and the banner shows `roles=<active> N/M`.
- **Given** two panels of the same agent, **When** each composes a chain, **Then** `.roles`/`.role` are panel-scoped and the Hub shows the live panel's chain (no cross-panel fossil).
- **Given** the verification matrix, **Then** thinking_os/adapter/golden/web suites pass and verify-hooks is clean.

## Work Log
- 2026-06-01 [claude]: F2 — `formula_composer.signals_from_prompt` derives action/domain/scope from the prompt so chains vary per task (proven: debug→debugger, audit→security_auditor); `advance-role.sh` (PostToolUse) advances `.role` by work phase, banner shows `roles=<active> N/M`. F1 — `.roles`/`.role`/`.learn-suggestions` panel-first (writer/reader/reset + COS_PER_PANEL_FILES); roles.py reuses `_newest_marker` for Hub. Cleanup: MemoryPage null-guards. Verified: thinking_os 1210, adapter 47, golden 6, web 31, verify-hooks clean, ui-build clean. Commits c8e1006·13d4336·1741a89·ff7485c·991b451·9a76162·c849939 pushed to origin. Note: `.git/hooks/pre-commit` deadlocks on ~15+ file commits (filed as follow-up).
