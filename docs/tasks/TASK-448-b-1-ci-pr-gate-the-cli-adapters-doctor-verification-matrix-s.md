---
id: TASK-448
title: "B-1 CI: PR-gate the cli/adapters/doctor verification-matrix suites (F-TST-2 CI-coverage illusion)"
swimlane: infra
kind: chore
epic: null
labels: [modularity-audit-pass3, ci, F-TST-2, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-19
started: 2026-06-19
completed: 2026-06-19
agent_session: ses-claude-20260619-063923-1c50
depends_on: []
blocked_by: []
references: []
---
# TASK-448: B-1 CI: PR-gate the cli/adapters/doctor verification-matrix suites (F-TST-2 CI-coverage illusion)

**Outcome (one sentence):** The Verification-Matrix suites that AGENTS.md prescribes for src/cli/*.py (test_cli.py) and src/adapters/** (test_adapters.py + test_adapter_parity.py) plus test_doctor.py run on every PR via a single-runner test-matrix job, instead of being deselected by `-m 'not slow'` and only running in the schedule-gated nightly job. Closes the CI-coverage illusion where the matrix contract is aspirational on PRs (root cause of the 2 prior CI-hidden RED breakages).

## Work Log
- 2026-06-19 [claude]: Edit ci.yml
- 2026-06-19 [claude]: Edit ci.yml
- 2026-06-19 [claude]: Edit block-hardcoded-literals.sh
- 2026-06-19 [claude]: committed c0e77b79 · 1 file
- 2026-06-19 [claude]: committed 6f1156a3 · 3 files
