---
id: TASK-030
title: "Role-* commands: dual-mode (composer JSON + interactive prose) + repo-aware input"
swimlane: infra
kind: refactor
epic: null
labels: [meta, role-prompts, repo-aware, ux]
status: archive
priority: P1
appetite: "1d"
created: 2026-05-25
started: 2026-05-25
completed: 2026-05-25
agent_session: ses-claude-20260524-224550-c745
depends_on: []
blocked_by: []
references: []
---
# TASK-030: Role-* commands: dual-mode (composer JSON + interactive prose) + repo-aware input

**Outcome (one sentence):** Each of 11 role-*.md agent SSOT files works for both human slash-command and composer dispatch — interactive auto-detects task/diff/stack/contracts from repo, returns prose review + embedded JSON envelope; composer path still returns JSON-only via SDK injection.

## Read First
- src/core/thinking_os/agents/reviewer.md — SSOT for one role (template applied first)
- src/core/thinking_os/tools/cognition.py — confirms `{{ XxxInput }}` is never substituted (dispatcher loads md verbatim + passes input_slice separately)
- docs/adapters/claude-sdk.md — composer pipeline contract

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a user invokes `/role-reviewer` (or any other `/role-*`) with no structured input,
- **When** Claude follows the new dual-mode prompt,
- **Then** Claude auto-detects task_id/scope/stack/nfr from repo, outputs prose review with the 6 sections, and appends a parseable JSON envelope at the bottom.

- **Given** the composer dispatches `cos_dispatch_formula_run(formula_id=reviewer)`,
- **When** input_slice with structured ReviewerInput JSON is attached,
- **Then** the agent returns JSON-only matching ReviewerOutput (back-compat preserved).

- **Given** the refactor script is re-run,
- **When** all 11 files already contain "two modes" sentinel,
- **Then** it reports 0 rewrote, 11 skipped (idempotent).

## Work Log
- 2026-05-25 [claude]: All 11 role-*.md SSOT dual-mode (composer JSON + interactive prose). refactor_agent_dual_mode.py idempotent. /review fol
