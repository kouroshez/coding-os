---
id: TASK-004
title: "Hook+observability pipeline cleanup (10-item audit)"
swimlane: infra
kind: refactor
epic: null
labels: [hooks, observability, noise-reduction, task-identity, persona]
status: complete
priority: P1
appetite: "1d"
created: 2026-05-07
started: null
completed: 2026-05-07
agent_session: ses-claude-20260507-085328-06cd
depends_on: []
blocked_by: []
references: []
---
# TASK-004: Hook+observability pipeline cleanup (10-item audit)

**Outcome (one sentence):** Hook firing cleaner: read-only Bash no longer fires false `[fire]`; check-capture-worked grep matches actual log order; reindex skips /tmp; tail timezone normalized; Stop hook description corrected; persona-aware task-mode marker classifies each prompt as formal/query/chore/adhoc/promote/system/gov-required so downstream hooks gate appropriately (Rule 18 honored without forcing TASK-NNN on Q&A).

## Read First
- core/hooks/registry.yaml
- core/hooks/enforce-verify.sh
- core/hooks/search-enforce-inventory.sh
- core/hooks/check-capture-worked.sh
- core/hooks/auto-reindex-docs.sh
- core/graph_os/tools/reindex_dispatch.py
- cli/tail_command.py
- core/hooks/nudge-thinking-os.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a `cos tail -f` running during a read-only session (`cos status`, `git log`, …)
- **When** the agent issues a non-task-done Bash command
- **Then** `enforce-verify` logs `skip` (not `fire`) and `search-enforce-inventory` emits no `[entry]` line; total hook log lines per Bash drop ≥ 50%

- **Given** a session where the agent edits ≥ 1 file
- **When** the Stop event fires
- **Then** `check-capture-worked` reports the correct Write/Edit count from `.hooks.log` (regex order matches actual log line layout) and never falsely classifies the session as `read-only-session`

- **Given** an Edit on a file under `/private/tmp/` or `/tmp/`
- **When** `auto-reindex-docs` dispatches
- **Then** `reindex_dispatch.dispatch` returns `status="skipped" reason="out-of-repo"` and writes nothing to graph_nodes

- **Given** a UTC-stamped hook line (`[…Z]`) and a local-stamped MCP line for the same wall-clock event
- **When** `cos tail` renders both
- **Then** they sort and display in identical local time (timezone normalized at the renderer)

- **Given** any UserPromptSubmit
- **When** the prompt classifier runs
- **Then** `$COS_AGENT_DIR/.task-mode` contains exactly one of `formal | propose-formal | query | chore | adhoc | promote | system | gov-required` per the persona decision matrix; downstream hooks read the marker and gate accordingly (query mode skips enforce-task-start / enforce-verify / capture-work-log; chore mode skips zoom / skill; system mode bypasses all)

- **Given** a graph_os call when Kuzu is empty
- **When** the same session issues a second graph_os call
- **Then** the Kuzu probe is skipped via a session-scoped negative cache (`/tmp/.cos-kuzu-empty-<sid>` or in-memory) and the SQLite path runs directly

- **Given** the registry description for hook `session-end`
- **When** an operator reads it
- **Then** the description states "fires on Stop = end-of-turn (not whole conversation)" so naming is unambiguous

## Work Log
- 2026-05-07 [claude]: Shipped 10-item audit + persona task-mode + G1 H-badge fix in commit 93b1d30. 21 files / 494 LOC. Verify matrix green: b
