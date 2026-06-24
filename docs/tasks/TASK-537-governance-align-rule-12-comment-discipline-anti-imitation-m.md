---
id: TASK-537
title: "governance: align Rule 12 comment-discipline \u2014 anti-imitation match-density clause + teach-why + fix implementer/formulas contradictions"
swimlane: docs
kind: docs
epic: null
labels: [governance, comments, dogfood, ready]
status: testing
priority: P2
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: null
agent_session: ses-claude-20260624-002336-1f4e
depends_on: []
blocked_by: []
references: []
---
# TASK-537: governance: align Rule 12 comment-discipline — anti-imitation match-density clause + teach-why + fix implementer/formulas contradictions

**Outcome (one sentence):** Neutralize the dogfood imitation loop behind agent comment-spam: the Claude Code harness instructs "match surrounding comment density", and src/core legacy is 25-34% comments / 33-45% of helpers carry docstrings, so agents copy the dense neighbor and override Rule 12. Make Rule 12 explicitly name that trap (match the density Rule 12 TARGETS, near-zero; treat dense code as tech-debt to thin on touch, never a pattern to extend), add the missing teach-why to the AGENTS.md index row, and remove the two pro-comment contradictions (implementer Step 7 framing + formulas-en.md:761).

## Read First
- docs/governance/critical-rules.md
- src/core/skills/clean-code/SKILL.md
- src/core/thinking_os/agents/implementer.md
- docs/code-os-core-docs/thinkingos-formulas/formulas-en.md

## Work Log
- 2026-06-24 [claude]: Deliberation: fix the imitation loop at the rule/skill layer (anti-imitation "match-density" clause in…
- 2026-06-24 [claude]: Edit critical-rules.md
- 2026-06-24 [claude]: Edit SKILL.md
- 2026-06-24 [claude]: Edit implementer.md
- 2026-06-24 [claude]: Edit formulas-en.md
- 2026-06-24 [claude]: Edit AGENTS.md
- 2026-06-24 [claude]: Verified: golden+adapter parity 11 passed (clean-code SKILL + role-implementer command propagation synced via make…
