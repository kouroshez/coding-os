---
id: TASK-996
title: "Measure the real per-run cost of an ablation arm before committing to a pilot"
swimlane: infra
kind: chore
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-08-16
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-996: Measure the real per-run cost of an ablation arm before committing to a pilot

**Outcome (one sentence):** The ablation protocol carries a measured cost per run taken from real executions, so the decision to fund or drop the 300-run pilot rests on a number rather than a guess.

## Work Log
- 2026-08-16 [claude]: Edit ablation_probe.py
- 2026-08-16 [claude]: Edit ablation-protocol.md
- 2026-08-16 [claude]: commit 38f3a3baca — feat(eval): preflight the ablation cost probe instead of guessing its price
- 2026-08-16 [claude]: Edit _init_scaffold.py
- 2026-08-16 [claude]: Edit _init_scaffold.py
- 2026-08-16 [claude]: Edit update.py
- 2026-08-16 [claude]: Edit update.py
- 2026-08-16 [claude]: Edit _init_scaffold.py
- 2026-08-16 [claude]: Edit _init_scaffold.py
- 2026-08-16 [claude]: Edit update.py
- 2026-08-16 [claude]: Edit test_stack_rule_refresh.py
- 2026-08-16 [claude]: Edit hub-architecture.md
- 2026-08-16 [claude]: Edit update.py
- 2026-08-16 [claude]: Edit update.py
- 2026-08-16 [claude]: Edit update.py
- 2026-08-16 [claude]: Edit hub-architecture.md
- 2026-08-16 [claude]: commit 93aa5c4fa6 — fix(cli): carry stack-rule corrections into installed projects on update
- 2026-08-16 [claude]: Recon of this machine settled what the probe needs: Docker 29.5.2 responds and SWE-bench Verified is reachable…
