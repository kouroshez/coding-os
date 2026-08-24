---
id: TASK-1027
title: "cos skill enable/disable strips every comment from .coding-os.yaml"
swimlane: cli
kind: bug
epic: null
labels: [cli, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-08-24
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1027: cos skill enable/disable strips every comment from .coding-os.yaml

**Outcome (one sentence):** A consumer's annotated .coding-os.yaml survives a skill toggle, so the file stays the documented config the operator wrote.

## Read First
- src/cli/_skill_project.py
- src/cli/skill_commands.py
- .coding-os.yaml

## Repro Steps
In this repo run `cos skill disable a11y` then `cos skill enable a11y`, then `git diff .coding-os.yaml`. Every comment block is gone and the list indentation is rewritten (17 lines removed from a 43-line file), because the toggle round-trips the config through a plain YAML load/dump. Observed 2026-08-24 while testing skill projection.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a .coding-os.yaml carrying comments
  **When** `cos skill disable X` then `cos skill enable X` runs
  **Then** `git diff` reports no change beyond the disabled_skills entry itself.
- **Given** the toggle needs to edit one key
  **When** it writes the file
  **Then** it uses a comment-preserving round-trip (ruamel round-trip loader or a targeted line edit), not yaml.safe_dump.

## Work Log
