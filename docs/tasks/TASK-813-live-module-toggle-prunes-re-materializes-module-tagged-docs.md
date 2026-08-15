---
id: TASK-813
title: "Live module toggle prunes/re-materializes module-tagged docs (F-B / rank 2, June DOC-4)"
swimlane: core
kind: feature
epic: modularity-completion
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-07-16
started: 2026-07-16
completed: 2026-07-16
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-813: Live module toggle prunes/re-materializes module-tagged docs (F-B / rank 2, June DOC-4)

**Outcome (one sentence):** Disabling a module after init strips its `| module:X`-tagged docs (backed up, guarded against user edits) and re-enabling re-materializes them, so the doc/reference surface tracks live module state instead of decaying after the first post-init toggle.

## Read First
- src/cli/module_commands.py
- src/cli/main.py
- src/cli/update.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** memory enabled at init then disabled live, **When** toggle_and_regen runs, **Then** memory-tagged scaffold docs are pruned (backed up); on re-enable they are re-materialized from scaffold source; a user-edited copy is NOT clobbered (backup + skip or warn).

Checklist:
- [ ] Add a doc-sync step to regen_after_toggle (or a `cos module sync-docs` one-shot invoked by it) that re-runs _apply_doc_conditions against scaffold sources for the toggled module.
- [ ] Disable: strip/backup tagged docs; Enable: re-materialize skipped-at-init docs.
- [ ] Guard: never clobber a doc whose content diverged from scaffold source (hash/backup); meta-repo guarded.
- [ ] Reuse _apply_doc_conditions (do NOT add a second engine, Rule 22).
- [ ] Tests: disable->tagged doc gone+backed up; enable->restored; edited-copy preserved.
- [ ] Verify: uv run pytest tests/test_cli.py -q + make docs-lint.

## Work Log
- 2026-07-16 [claude]: Edit main.py
- 2026-07-16 [claude]: Edit module_commands.py
- 2026-07-16 [claude]: Edit module_commands.py
- 2026-07-16 [claude]: Edit doctor.py
- 2026-07-16 [claude]: Edit test_cli.py
- 2026-07-16 [claude]: Implemented live-toggle doc sync + corrected TASK-812's doc_drift. KEY FINDING: _apply_doc_conditions STRIPS the `|…
- 2026-07-16 [claude]: commit eb898528a2 — feat(core): live-toggle doc prune/restore + correct doc_drift source mapping (F-B)
