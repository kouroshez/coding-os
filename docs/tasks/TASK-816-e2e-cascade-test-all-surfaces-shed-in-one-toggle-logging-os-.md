---
id: TASK-816
title: "E2E cascade test (all surfaces shed in one toggle) + logging_os wiring on toggle rollback/refusal (F-G / ranks 14+13)"
swimlane: core
kind: test
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
# TASK-816: E2E cascade test (all surfaces shed in one toggle) + logging_os wiring on toggle rollback/refusal (F-G / ranks 14+13)

**Outcome (one sentence):** One integration test pins the toggle orchestrator so dropping either cascade line fails CI, and the toggle path emits queryable logging_os events on rollback/refusal so a headless CI/nightly toggle failure is discoverable via cos_log_query instead of only a returned string.

## Read First
- tests/test_modularity_toggle.py
- tests/test_module_gating_smoke.py
- src/cli/module_commands.py
- src/core/logging_os/bridge.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a fully-linked fixture project, **When** cos module disable runs through toggle_and_regen UNMOCKED, **Then** the test asserts allowlist entry removed + AGENTS.md block gone + skill symlink gone + command symlink gone together (dropping module_commands.py:246 or :247 fails it); **and** a forced regen failure writes a log_events row queryable by cos_log_query.
Checklist:
- [ ] Integration test driving toggle_and_regen unmocked on a linked fixture; assert every surface shed at once.
- [ ] Emit logging_os warn/error at regen-failure rollback + dependency-refusal branches (scope 'cli.module') via the stdlib->logging_os bridge.
- [ ] Test asserts a log_events row on forced regen failure.
- [ ] Keep it PR-fast (not @slow) or justify the mark.
- [ ] Verify: uv run pytest tests/test_modularity_toggle.py tests/test_module_gating_smoke.py -q.

## Work Log
- 2026-07-16 [claude]: Edit module_commands.py
- 2026-07-16 [claude]: Edit module_commands.py
- 2026-07-16 [claude]: Edit test_cli.py
- 2026-07-16 [claude]: test_toggle_and_regen_sheds_all_surfaces_at_once: inits a full-profile consumer, calls toggle_and_regen('tasks',…
- 2026-07-16 [claude]: commit 28d3678ed4 — test(core): E2E cascade shed-all-surfaces + toggle refusal/rollback logging (F-G)
