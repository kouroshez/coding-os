---
id: TASK-974
title: "Gate the nightly slow suite and run macOS + a11y on every PR"
swimlane: infra
kind: chore
epic: null
labels: [ci, P1, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-14
started: 2026-08-14
completed: 2026-08-14
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-974: Gate the nightly slow suite and run macOS + a11y on every PR

**Outcome (one sentence):** Every suite the repo already pays to run can actually fail the build, so a regression it catches cannot reach main under a green CI Pass.

## Work Log
- 2026-08-14 [claude]: Edit ci.yml
- 2026-08-14 [claude]: Edit ci.yml
- 2026-08-14 [claude]: Edit ci.yml
- 2026-08-14 [claude]: Edit test_ci_pass_gates.py
- 2026-08-14 [claude]: Edit test_ci_pass_gates.py
- 2026-08-14 [claude]: Edit test_ci_pass_gates.py
- 2026-08-14 [claude]: Edit msg8.txt
- 2026-08-14 [claude]: commit 6bfffe46b6 — ci: gate the nightly suite, run a11y and a macOS smoke on every push
- 2026-08-14 [claude]: Fixed in 6bfffe46. Ran the a11y suite locally first (7 passed) before wiring it in, so CI is not the place it gets…
- 2026-08-14 [claude]: Status transitioned to complete via cos task-done.
- 2026-08-14 [claude]: Edit stack_maturity.py
- 2026-08-14 [claude]: Edit list_stacks.py
- 2026-08-14 [claude]: Edit list_stacks.py
- 2026-08-14 [claude]: Edit list_stacks.py
- 2026-08-14 [claude]: Edit test_stack_maturity.py
- 2026-08-14 [claude]: Edit README.md
- 2026-08-14 [claude]: Edit README.md
- 2026-08-14 [claude]: Edit README.md
- 2026-08-14 [claude]: Edit msg9.txt
- 2026-08-14 [claude]: commit 49da33dc70 — feat(stacks): mark which stacks CI actually builds, derived from the matrix
