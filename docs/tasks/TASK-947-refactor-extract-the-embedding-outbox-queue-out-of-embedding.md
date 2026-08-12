---
id: TASK-947
title: "refactor: extract the embedding outbox queue out of embeddings.py"
swimlane: "thinking_os"
kind: refactor
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-12
started: 2026-08-12
completed: 2026-08-12
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-947: refactor: extract the embedding outbox queue out of embeddings.py

**Outcome (one sentence):** embeddings.py is back under its recorded size ratchet, with the durable outbox queue living in its own module and every existing caller and monkeypatch target still resolving.

## Read First
- src/core/thinking_os/embeddings.py
- src/core/hooks/_helpers/drain_embedding_outbox.py
- tests/test_file_size_budget.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the file-size ratchet **When** tests/test_file_size_budget.py runs **Then** it passes with embeddings.py at or below its recorded number. **Given** the hook helper that calls embeddings.drain_outbox **When** it runs **Then** the name still resolves and the drain behaves identically. **Given** the thinking_os suite **When** it runs **Then** it is green on the matrix command.

## Work Log
- 2026-08-12 [claude]: commit a6871ea7b0 — refactor(thinking_os): move the embedding outbox into its own module
- 2026-08-12 [claude]: embeddings.py 953 -> 879; ratchet green; 1572 thinking_os tests + server --test pass; real hook helper drained 64 rows.
- 2026-08-12 [claude]: Status transitioned to complete via cos task-done.
