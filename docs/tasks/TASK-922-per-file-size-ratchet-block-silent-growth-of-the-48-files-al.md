---
id: TASK-922
title: "Per-file size ratchet: block silent growth of the 48 files already over 800 lines"
swimlane: core
kind: chore
epic: null
labels: [ci, tech-debt, ready]
status: testing
priority: P1
appetite: 1d
created: 2026-08-10
started: 2026-08-10
completed: null
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-922: Per-file size ratchet: block silent growth of the 48 files already over 800 lines

**Outcome (one sentence):** tests/test_file_size_budget.py fails when any tracked non-scaffold .py file grows beyond its recorded baseline, or when a file not in the baseline crosses 800 lines — so the incremental-growth path that produced the 3159-line server.py cannot recur silently.

## Work Log
- 2026-08-10 [claude]: Edit test_file_size_budget.py
- 2026-08-10 [claude]: Edit test_file_size_budget.py
- 2026-08-10 [claude]: Edit ci-gates.md
- 2026-08-10 [claude]: Edit KNOWN_LIMITATIONS.md
- 2026-08-10 [claude]: Edit ci-gates.md
- 2026-08-10 [claude]: commit bd15d39646 — chore(deps): sync uv.lock to the 0.3.10 version bump
