---
id: TASK-507
title: "Friction-before-destruction hook \u2014 warn on large net-deletion/overwrite of load-bearing files (git provenance pointer)"
swimlane: core
kind: feature
epic: null
labels: [governance, hooks, safety, ready]
status: in_progress
priority: P2
appetite: 1d
created: 2026-06-21
started: 2026-06-21
completed: null
agent_session: ses-claude-20260620-223021-5083
depends_on: []
blocked_by: []
references: []
---
# TASK-507: Friction-before-destruction hook — warn on large net-deletion/overwrite of load-bearing files (git provenance pointer)

**Outcome (one sentence):** A PreToolUse Write|Edit|MultiEdit hook (warn-destructive-edit.sh + _helpers/destructive_edit_check.py) that fires friction-before-destruction: when an agent performs a large net-deletion or wholesale overwrite of a load-bearing file (docs/** contract layer + the existing rag-config.yaml::graph.enforce_context_on code globs — NO new config), it emits ONE stderr line naming the commit that last touched the file + the removed line count + the exact `git log -L`/`git show` pull command, then exits 0 (WARN). Self-throttling: silent + exit 0 on the 95% of edits below threshold or on non-load-bearing files. Fail-open on any internal error (no git, not a repo, bad JSON). Mirrors enforce-graph-context env contract: COS_DESTRUCTIVE_GUARD=off|warn|strict (default warn), COS_DESTRUCTIVE_GUARD_MIN_LINES (default 12). NO new DB table, MCP tool, UI, or reason-store (does NOT revive the retired audit subsystem; read legs stay git-native). Registered in registry.yaml, adapters regenerated.

## Read First
- docs/engineering/destructive-edit-guard.md
- src/core/hooks/enforce-graph-context.sh
- src/core/hooks/_helpers/graph_context_match.py
- src/core/hooks/registry.yaml
- docs/governance/critical-rules.md

## Acceptance — *this IS the Definition of Done*
- **Given** an Edit removing >= MIN_LINES net lines from a docs/** or enforce_context_on file **When** the PreToolUse hook runs **Then** it prints one warning line (commit %h + subject + removed-line count + the `git log -L`/`git show` pull command) on stderr and exits 0.
- **Given** a small edit (< MIN_LINES) OR a non-load-bearing file (e.g. /tmp/x, node_modules) **When** the hook runs **Then** it prints nothing and exits 0.
- **Given** a Write that creates a NEW file or grows an existing file **When** the hook runs **Then** there is no warning (not a deletion) and it exits 0.
- **Given** COS_DESTRUCTIVE_GUARD=strict plus a large deletion of a load-bearing file **When** the hook runs **Then** it BLOCKs with exit 2 and a remediation message.
- **Given** malformed stdin / git absent / not a repo / COS_DESTRUCTIVE_GUARD=off **When** the hook runs **Then** it fails open (exit 0, no block).
- **Given** `make verify-hooks` and the new tests/test_warn_destructive_edit.py **When** they run **Then** shellcheck + bash -n pass and all behavior tests are green.

## Work Log
- 2026-06-21 [claude]: Edit destructive-edit-guard.md
- 2026-06-21 [claude]: Edit destructive_edit_check.py
- 2026-06-21 [claude]: Edit warn-destructive-edit.sh
- 2026-06-21 [claude]: Edit registry.yaml
- 2026-06-21 [claude]: Edit test_warn_destructive_edit.py
- 2026-06-21 [claude]: commit 5592167099 — test(modularity): consumer-disable harness sheds skill/command/tool + pins DOC-4 gap (TASK-505)
