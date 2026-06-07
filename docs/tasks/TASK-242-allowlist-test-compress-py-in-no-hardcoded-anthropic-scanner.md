---
id: TASK-242
title: "Allowlist test_compress.py in no-hardcoded-anthropic scanner (test asserts a literal model id)"
swimlane: core
kind: chore
epic: null
labels: [ready]
status: testing
priority: P2
appetite: 30m
created: 2026-06-07
started: 2026-06-07
completed: null
agent_session: ses-claude-20260607-001830-03d2
depends_on: []
blocked_by: []
references: []
---
# TASK-242: Allowlist test_compress.py in no-hardcoded-anthropic scanner (test asserts a literal model id)

**Outcome (one sentence):** tests/test_no_hardcoded_anthropic.py allowlists src/core/thinking_os/tests/test_compress.py (it legitimately asserts _stamp_provenance echoes the model id 'claude-haiku-4-5'), so the parametrized scan is green — mirroring the existing compress.py allowlist entry.

## Work Log
