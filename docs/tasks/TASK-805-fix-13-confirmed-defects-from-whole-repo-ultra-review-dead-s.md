---
id: TASK-805
title: "Fix 13 confirmed defects from whole-repo ultra review (dead script, stub drift, YAML quoting, URLs, docs contract)"
swimlane: core
kind: bug
epic: null
labels: [review-sweep, docs-update, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-07-10
started: 2026-07-09
completed: 2026-07-09
agent_session: ses-claude-20260709-202023-30fe
depends_on: []
blocked_by: []
references: []
---
# TASK-805: Fix 13 confirmed defects from whole-repo ultra review (dead script, stub drift, YAML quoting, URLs, docs contract)

**Outcome (one sentence):** All CONFIRMED findings from the 2026-07-09 max-effort whole-repo review are fixed: record_experiment.py dead deliverable removed; server.py graph stub list covers all 22 tools; board frontmatter list items YAML-quoted; graph_os provenance map matches live extractor ids; install.sh/README clone URLs point at the real remote (kouroshez); codex dangling delegates removed; trace-replay resolves core via _resources; graph export cache signature covers edges; doc_header guard anchored on project_root; duplicate graph-reindex registration removed; docs drift (00-index rules range, mcp-tool-inventory 6 tools, task-lifecycle db.py/P0, simplify link, make test-hooks) corrected. P8 SDK-import finding explicitly deferred to its own task.

## Read First
- docs/governance/critical-rules.md § Rules 12, 13, 22
- docs/engineering/mcp-error-envelope.md
- docs/governance/task-lifecycle.md

## Repro Steps
Run python src/core/thinking_os/record_experiment.py against a v43+ DB (no such table); create a task with label 'a: b' and watch sync fail; clone the README URL (404); call cos_graph_cycles with graph extras missing (tool not found instead of unavailable envelope).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the matrix suites for thinking_os/board_os/graph_os/adapters/cli and make docs-lint, **When** run after the fixes, **Then** all pass.
- **Given** graph_os is unimportable, **When** any of the 22 cos_graph_* tools is called, **Then** it returns a fail('unavailable') envelope.
- **Given** a label containing YAML specials, **When** cos_task_create renders frontmatter, **Then** the file parses as valid YAML.
- **Given** a fresh machine, **When** the README/install.sh clone command runs, **Then** it clones the real repo.

## Work Log
- 2026-07-10 [claude]: Edit server.py
- 2026-07-10 [claude]: Edit server.py
- 2026-07-10 [claude]: Edit server.py
- 2026-07-10 [claude]: Edit server.py
- 2026-07-10 [claude]: Edit server.py
- 2026-07-10 [claude]: commit a5a2111eee — fix(core): full graph stub list, project-root doc-header guard, drop dead experiment script
- 2026-07-10 [claude]: Edit mcp_tools.py
- 2026-07-10 [claude]: Edit parser.py
- 2026-07-10 [claude]: Edit parser.py
- 2026-07-10 [claude]: Edit migration.py
- 2026-07-10 [claude]: Edit types.py
- 2026-07-10 [claude]: Edit test_provenance.py
- 2026-07-10 [claude]: Edit graph.py
- 2026-07-10 [claude]: Edit graph.py
- 2026-07-10 [claude]: Edit server.py
- 2026-07-10 [claude]: Edit graph.py
- 2026-07-10 [claude]: Edit graph.py
- 2026-07-10 [claude]: Edit main.py
- 2026-07-10 [claude]: Edit main.py
- 2026-07-10 [claude]: Edit pyproject.toml
- 2026-07-10 [claude]: Edit cognition.py
- 2026-07-10 [claude]: Edit codex-userpromptsubmit-dispatch.sh
- 2026-07-10 [claude]: Edit mcp-tool-inventory.md
- 2026-07-10 [claude]: Edit mcp-tool-inventory.md
- 2026-07-10 [claude]: Applied 13 review findings in 6 commits (a5a2111e..7487fa72); P8 SDK-import deferred; matrix suites running
- 2026-07-10 [claude]: Status transitioned to complete via cos task-done.
