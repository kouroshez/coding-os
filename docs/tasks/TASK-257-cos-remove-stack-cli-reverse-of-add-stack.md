---
id: TASK-257
title: "cos remove-stack CLI (reverse of add-stack)"
swimlane: cli
kind: feature
epic: kernel-overrides
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-257: cos remove-stack CLI (reverse of add-stack)

**Outcome (one sentence):** Add cos remove-stack as the reverse of add-stack (recompose, unlink skills, regen AGENTS.md, backup).

## Read First
- src/cli/add_stack.py — the add path to reverse (templates append, _apply_template, recompose_for_added_stack, _link_stack_skills, stack_history).
- src/cli/stack_registry.py — load_stack_registry.
- .coding-os.yaml — the templates list to mutate (comment-preserving).

## Context / Approach
Build cos remove-stack: drop the stack from .coding-os.yaml::templates, recompose composed configs, unlink its skills, regenerate AGENTS.md, write a backup + a stack_history entry. Use comment-preserving YAML (ruamel) to avoid round-trip loss. Unblocks the Config "remove stack" action (currently disabled because no producer exists).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an installed stack, **When** remove-stack runs, **Then** it is dropped from templates and its skills are unlinked.
- **Given** the removal completes, **When** inspected, **Then** AGENTS.md is regenerated and no orphaned composed config remains.

## Work Log
- 2026-06-08 [claude]: Implemented `cos remove-stack` (src/cli/remove_stack.py) as the reverse of add-stack: drops the stack from .coding-os.ya
- 2026-06-08 [claude]: Status transitioned to complete via cos task-done.
