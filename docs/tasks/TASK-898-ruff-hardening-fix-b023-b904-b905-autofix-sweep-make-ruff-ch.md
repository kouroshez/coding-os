---
id: TASK-898
title: "Ruff hardening: fix B023/B904/B905, autofix sweep, make ruff check blocking in CI"
swimlane: core
kind: chore
epic: null
labels: [quality, ci, lint, ready]
status: testing
priority: P1
appetite: 1d
created: 2026-08-08
started: 2026-08-07
completed: null
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-898: Ruff hardening: fix B023/B904/B905, autofix sweep, make ruff check blocking in CI

**Outcome (one sentence):** ruff check src/ tests/ exits 0 and ci.yml runs it without || true

## Work Log
- 2026-08-08 [claude]: Edit main.py
- 2026-08-08 [claude]: Edit test_code_shell_fallback.py
- 2026-08-08 [claude]: Edit cognition.py
- 2026-08-08 [claude]: Edit graph_commands.py
- 2026-08-08 [claude]: Edit main.py
- 2026-08-08 [claude]: Edit preset_commands.py
- 2026-08-08 [claude]: Edit registry.py
- 2026-08-08 [claude]: Edit server.py
- 2026-08-08 [claude]: Edit server.py
- 2026-08-08 [claude]: Edit main.py
- 2026-08-08 [claude]: Edit test_indexing_harness.py
- 2026-08-08 [claude]: Edit test_sanitizer.py
- 2026-08-08 [claude]: Edit test_sanitizer.py
- 2026-08-08 [claude]: Edit registry.py
- 2026-08-08 [claude]: Edit code_python.py
- 2026-08-08 [claude]: Edit db_reset.py
- 2026-08-08 [claude]: Edit db_reset.py
- 2026-08-08 [claude]: Edit update.py
- 2026-08-08 [claude]: Edit test_block_shared_tree_edit.py
- 2026-08-08 [claude]: Edit test_block_shared_tree_edit.py
- 2026-08-08 [claude]: Edit audit_mcp_tools.py
- 2026-08-08 [claude]: Edit contrast_check.py
- 2026-08-08 [claude]: Edit contrast_check.py
- 2026-08-08 [claude]: Edit contrast_check.py
- 2026-08-08 [claude]: Edit contrast_check.py
- 2026-08-08 [claude]: Edit deltae_check.py
- 2026-08-08 [claude]: Edit update.py
- 2026-08-08 [claude]: Edit test_embeddings.py
- 2026-08-08 [claude]: Edit hub.py
- 2026-08-08 [claude]: Edit test_no_phantom_tool_refs.py
- 2026-08-08 [claude]: Edit database.py
- 2026-08-08 [claude]: Edit test_cli.py
- 2026-08-08 [claude]: Edit test_cli.py
- 2026-08-08 [claude]: Edit test_cli.py
- 2026-08-08 [claude]: Edit pyproject.toml
- 2026-08-08 [claude]: Edit pyproject.toml
- 2026-08-08 [claude]: Edit ci.yml
- 2026-08-08 [claude]: Edit test_file_size_budget.py
- 2026-08-08 [claude]: Chose baseline-burndown (fix bug-rules, ignore 3 style rules with counts) over fixing all 247 —…
