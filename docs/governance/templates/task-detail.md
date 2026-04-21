<!-- domain:DOCS | layer:reference | ssot:true | updated:2026-04-07 -->
# Task Detail Template (reference)

Purpose: Canonical template for task detail files that `make task-create` generates inside projects. Updated whenever the scaffold template changes.
Read when: Repairing a broken task file, or auditing the task-lifecycle contract.
Skip when: Creating a new task — use `make task-create NUM=N TITLE="[DOMAIN] description"` instead.
Read next: `core/scripts/task-create.sh` for the generator, `templates/_base/scaffold/docs/governance/templates/task-detail.md` for the shipping template.

## Canonical Sections

Every generated task file has these sections in order:

1. `## Goal` — 1-3 sentence statement of the outcome
2. `## Read First` — REF codes + file paths the agent should load before acting
3. `## Source of Truth` — target code files the task will produce/modify
4. `## Scope` with `### In` and `### Out` subsections
5. `## Requirements` — numbered Given/When/Then acceptance criteria
6. `## Dependencies` — list of prerequisite TASK-### refs
7. `## Open Questions` — "None." or unresolved items
8. `## Rabbit Holes` — "None." or known traps
9. `## Verification` — commands to run before marking done
10. `## Notes` — optional working notes and session checkpoints

## Source

The live template shipped to new projects lives at `templates/_base/scaffold/docs/governance/templates/task-detail.md`. It uses double-curly-brace placeholders for `DOMAIN` and `DATE` that `task-create.sh` substitutes at generation time (the exact placeholder syntax is documented in the shipping template itself, not inlined here so this reference doc stays lint-clean).

Any changes to the section contract must be made in both:

- `templates/_base/scaffold/docs/governance/templates/task-detail.md` (the shipping scaffold)
- `core/thinking_os/task_parser.py` (the Phase C parser that reads the sections back)
- `core/thinking_os/tests/test_task_parser.py` (the regression tests)
