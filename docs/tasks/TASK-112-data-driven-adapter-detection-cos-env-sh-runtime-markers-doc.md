---
id: TASK-112
title: "Data-driven adapter detection — cos-env.sh runtime markers, doctor loaders, drop speculative GEMINI literals, .sh hardcode test"
swimlane: infra
kind: refactor
epic: hook-remediation
labels: [adapter, data-driven, cli, audit-n8]
status: icebox
priority: P2
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-112: Data-driven adapter detection — cos-env.sh runtime markers, doctor loaders, drop speculative GEMINI literals, .sh hardcode test

**Outcome (one sentence):** cos-env.sh agent detection reads adapter.yaml::runtime_env_markers (not a hardcoded if/elif); doctor.py mcp-loader dispatch generalized/registered so Cursor's diagnostic runs; speculative GEMINI_* literals removed; hardcoded-literal test extended to src/core/hooks/*.sh.

## Read First
- src/core/hooks/cos-env.sh
- src/cli/doctor.py
- tests/test_no_hardcoded_stacks.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
