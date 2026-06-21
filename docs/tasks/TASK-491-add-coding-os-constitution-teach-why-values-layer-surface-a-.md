---
id: TASK-491
title: "Add coding-os Constitution (teach-why values layer) + surface a compressed slice at SessionStart"
swimlane: docs
kind: feature
epic: teach-why-alignment
labels: [teach-why, constitution, alignment, governance, ready]
status: complete
priority: P1
appetite: 2d
created: 2026-06-21
started: 2026-06-20
completed: 2026-06-20
agent_session: ses-claude-20260620-185936-c751
depends_on: []
blocked_by: []
references: []
---
# TASK-491: Add coding-os Constitution (teach-why values layer) + surface a compressed slice at SessionStart

**Outcome (one sentence):** Install the causal "principle/character" layer that Anthropic's "Teaching Claude Why" shows generalizes out-of-distribution where pure enforcement (our 26 hard-BLOCK hooks of 87) cannot. Deliver ONE docs/governance/constitution.md (<=120 lines, with Nav breadcrumb) stating the 6-8 values coding-os actually optimizes — SSOT-first (P1), minimal-context (P3), diff-minimal (P4), dogfood (P5), agent-agnostic (P2), docs-are-the-contract (Rule 19), anti-overengineering (Rule 22), autonomous-but-reversible — each with a one-sentence WHY and a DOWN-only link to the rule(s) it generates in critical-rules.md (no rationale duplicated -> P1). Then session-context.sh injects a compressed ~10-line slice into the EXISTING SessionStart additionalContext envelope (hidden agent channel, startup/resume only, suppressed on `compact` exactly like the Agent Digest). This is the keystone the other 6 tasks point at; written agent-facing and concrete to THIS repo's stakes (symlink blast radius to all consumers), not a philosophy manifesto.

## Read First
- docs/governance/critical-rules.md
- docs/governance/wrapper-derivation.md
- src/core/hooks/session-context.sh
- src/core/rules/transparency-banner.md
- docs/engineering/state-files.md
- CLAUDE.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh SessionStart (startup OR resume), **When** session-context.sh runs, **Then** the constitution slice appears in the hidden additionalContext envelope (NOT stderr) and is suppressed on source=compact.
- **Given** docs/governance/constitution.md, **When** `make docs-lint` runs, **Then** it passes; the file is <=120 lines and carries a `> Nav:` breadcrumb.
- **Given** the constitution authored, **When** a reviewer checks each value, **Then** each links DOWN to the rule(s) it generates in critical-rules.md (one direction only) and no rule rationale text is duplicated (P1 SSOT).
- **Given** AGENTS.md, **When** rendered, **Then** it references constitution.md as the values SSOT (one line).
- **Given** the full change set, **When** verifying, **Then** `make docs-lint` + `make verify-hooks` are GREEN. Execution requires a `governance`/`docs-update` task marker (Rule 7) and an atomic edit of the live-symlinked session-context.sh.

## Work Log
- 2026-06-21 [claude]: commit 75365afdc0 — chore(board): archive 2 closed tasks; add 10 Constitution/values-layer tasks
- 2026-06-21 [claude]: Edit constitution.md
- 2026-06-21 [claude]: Edit session-context.sh
- 2026-06-21 [claude]: Edit AGENTS.md
- 2026-06-21 [claude]: commit 99b4fc95a0 — feat(core): add coding-os Constitution (teach-why values layer) + surface slice at SessionStart
- 2026-06-21 [claude]: Authored docs/governance/constitution.md (8 values, down-only links to critical-rules.md, delimited SLICE block, 39…
