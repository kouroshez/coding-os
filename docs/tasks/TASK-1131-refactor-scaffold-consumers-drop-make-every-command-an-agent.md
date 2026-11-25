---
id: TASK-1131
title: "refactor(scaffold): consumers drop make; every command an agent is told to run starts with cos"
swimlane: templates
kind: refactor
epic: null
labels: [docs-update, governance, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-11-25
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1131: refactor(scaffold): consumers drop make; every command an agent is told to run starts with cos

**Outcome (one sentence):** A consumer project ships no Makefile.base or Makefile.stacks, and its AGENTS.md, rules, skills and docs name only cos commands, with the stack's lint and test reachable through cos.

## Read First
- src/templates/_base/Makefile.base
- src/cli/renderer.py
- src/cli/_init_phase.py
- src/cli/update.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh scaffold, **When** its files are listed, **Then** there is no .coding-os/Makefile.base or Makefile.stacks and no Makefile written by cos.
- **Given** the shipped AGENTS.md, rules, skills and docs, **When** grepped for `make <target>`, **Then** nothing matches outside a user-owned file.
- **Given** a stack with lint/test commands in stack.yaml, **When** the agent runs the cos command named in AGENTS.md, **Then** those commands run.
- **Given** an existing project whose Makefile includes Makefile.base, **When** `cos update` runs, **Then** the include lines and cos-owned files are removed and the user's own targets are kept.

## Work Log
