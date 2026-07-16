---
id: TASK-245
title: "Onboarding: onboarder chat role + formula-safe wiring"
swimlane: core
kind: feature
epic: hub-redesign
labels: [ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260608-024900-f2b0
depends_on: []
blocked_by: []
references: []
---
# TASK-245: Onboarding: onboarder chat role + formula-safe wiring

**Outcome (one sentence):** Add an onboarder chat role that interviews the user and drafts product docs after cos init, without breaking the 11-role formula ordering.

## Read First
- src/core/thinking_os/agents/documenter.md — agent-prompt format to mirror.
- src/core/thinking_os/formula_composer.py (lines ~41-46) — globs agents/*.md and reads `canonical_order`; onboarder.md must NOT perturb the 11-role ordering.
- src/core/web/routes/cognition.py — `_role_system_prompt` + `_role_names` (how a role .md becomes a chat system prompt; roles endpoint globs agents/*.md).
- docs/governance/docs-system.md — the doc layering the onboarder must fill.

## Context / Approach
Add src/core/thinking_os/agents/onboarder.md — a size-adaptive doc interviewer (scope pick → 3-7 one-at-a-time questions → draft docs/** → preview/approve), capped to avoid Spec-Kit-style over-generation. KEY RISK: formula_composer ALSO globs agents/*.md, so give onboarder.md frontmatter the formula loader ignores (no formula_ref / canonical_order) so the 11 semantic roles keep their order. Verify both the roles picker and the compose chain after adding.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a new chat with role=onboarder, **When** started, **Then** a size-adaptive doc interview runs one question at a time.
- **Given** onboarder.md added, **When** formula_composer loads, **Then** the 11 semantic roles keep their canonical order (no break).

## Work Log
- 2026-06-08 [claude]: Added agents/onboarder.md (chat-only role, no canonical_order so the 11-role chain is intact); load_agent_registry skips
