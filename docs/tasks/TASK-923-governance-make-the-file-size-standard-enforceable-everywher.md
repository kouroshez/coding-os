---
id: TASK-923
title: "governance: make the file-size standard enforceable everywhere (rule + skill + write-time hook)"
swimlane: core
kind: chore
epic: null
labels: [governance, hooks, ready]
status: in_progress
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
# TASK-923: governance: make the file-size standard enforceable everywhere (rule + skill + write-time hook)

**Outcome (one sentence):** A file over the 800-line standard can no longer be authored in coding-os or in any consumer project: the always-active rule and the clean-code skill state the ceiling, and the existing PreToolUse hook blocks a Write that would create one — reaching consumers through the live-symlink propagation that already exists, with no new hook, registry entry, or adapter template.

## Work Log
- 2026-08-10 [claude]: Edit anti-overengineering.md
- 2026-08-10 [claude]: Edit anti-overengineering.md
- 2026-08-10 [claude]: Edit anti-overengineering.md
- 2026-08-10 [claude]: Edit SKILL.md
- 2026-08-10 [claude]: Edit block-bad-patterns.sh
- 2026-08-10 [claude]: Edit test_hooks_file_size.py
- 2026-08-10 [claude]: Edit check-file-size.sh
- 2026-08-10 [claude]: Edit Makefile.base
- 2026-08-10 [claude]: Edit Makefile.base
- 2026-08-10 [claude]: Edit registry.yaml
- 2026-08-10 [claude]: Edit ci-gates.md
- 2026-08-10 [claude]: commit 859425a4d8 — feat(quality): enforce an 800-line file ceiling at write time and in consumers
- 2026-08-10 [claude]: Edit _server_runtime.py
- 2026-08-10 [claude]: Edit _server_runtime.py
- 2026-08-10 [claude]: Edit pyproject.toml
- 2026-08-10 [claude]: Edit test_brain_hardening.py
- 2026-08-10 [claude]: Edit test_brain_hardening.py
- 2026-08-10 [claude]: commit 4d12c4deeb — refactor(thinking_os): split the 3159-line server.py into a facade plus domain modules
- 2026-08-10 [claude]: Edit anti-overengineering.md
- 2026-08-10 [claude]: Edit anti-overengineering.md
- 2026-08-10 [claude]: Edit SKILL.md
- 2026-08-10 [claude]: Edit block-bad-patterns.sh
- 2026-08-10 [claude]: Edit check-file-size.sh
- 2026-08-10 [claude]: Edit check-file-size.sh
- 2026-08-10 [claude]: Edit check-file-size.sh
- 2026-08-10 [claude]: Edit check-file-size.sh
- 2026-08-10 [claude]: Edit test_hooks_file_size.py
- 2026-08-10 [claude]: Edit test_hooks_file_size.py
- 2026-08-10 [claude]: Edit ci-gates.md
- 2026-08-10 [claude]: Edit SKILL.md
- 2026-08-10 [claude]: Edit Makefile.base
- 2026-08-10 [claude]: check-file-size.sh deadlocked in bash heredoc_write on `done <<< "$candidates"` — the whole-repo default (282KB…
- 2026-08-10 [claude]: Edit check_file_size.py
- 2026-08-10 [claude]: Edit doctor_checks_quality.py
- 2026-08-10 [claude]: Edit doctor_checks_quality.py
- 2026-08-10 [claude]: Edit doctor_checks_quality.py
- 2026-08-10 [claude]: Edit check_file_size.py
- 2026-08-10 [claude]: Edit health.py
- 2026-08-10 [claude]: Edit test_file_size_scanner.py
- 2026-08-10 [claude]: Edit raptor-consolidation.md
- 2026-08-10 [claude]: Edit anti-overengineering.md
- 2026-08-10 [claude]: Edit check_file_size.py
- 2026-08-10 [claude]: Edit check_file_size.py
