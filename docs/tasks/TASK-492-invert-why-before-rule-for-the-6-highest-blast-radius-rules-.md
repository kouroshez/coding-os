---
id: TASK-492
title: "Invert WHY-before-rule for the 6 highest-blast-radius rules + lead BLOCK messages with the principle"
swimlane: core
kind: refactor
epic: teach-why-alignment
labels: [teach-why, hooks, rules, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-21
started: null
completed: null
agent_session: null
depends_on: [TASK-491]
blocked_by: []
references: []
---

# TASK-492: Invert WHY-before-rule for the 6 highest-blast-radius rules + lead BLOCK messages with the principle

**Outcome (one sentence):** Today the WHY is wired backwards: critical-rules.md is explicitly a POST-block reference ("Read when: a hook just blocked an action"), so on the common path the agent meets the bare imperative and fetches the rationale only after being stopped. The article's lesson 3 + Claude's constitution ("explain the reasoning behind any rules so the model could construct them itself") say principle must arrive WITH/BEFORE the behavior to generalize OOD. For the load-bearing rules (0 docs-first, 22 anti-overengineering, 23 trunk-git, 24 commit-msg, 25 semantic-ops), add a one-clause inline WHY next to the imperative in AGENTS.md (one clause each — the 120-line ceiling forbids paragraphs; the long tail stays in critical-rules.md), and rewrite the BLOCK stderr messages of the corresponding enforcement hooks to LEAD with the principle clause before the repair command. Reword only — add no new hooks.

## Read First
- CLAUDE.md
- docs/governance/critical-rules.md
- src/core/hooks/enforce-doc-anchor.sh
- src/core/hooks/enforce-skill.sh
- src/core/hooks/registry.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** AGENTS.md, **When** rendered, **Then** rules 0/22/23/24/25 each carry a <=1-clause inline WHY and the file stays <=120 lines.
- **Given** a BLOCK from enforce-doc-anchor / enforce-skill / branch-guard / enforce-commit-message / enforce-task-transition, **When** the message prints to stderr, **Then** its FIRST line is the principle (why) and the repair command follows it.
- **Given** the change set, **When** verifying, **Then** no new hook is added (messages reworded only) and `make verify-hooks` + `make docs-lint` are GREEN. Live-symlinked hooks edited atomically (Rule 23); governance marker required (Rule 7).

## Work Log
