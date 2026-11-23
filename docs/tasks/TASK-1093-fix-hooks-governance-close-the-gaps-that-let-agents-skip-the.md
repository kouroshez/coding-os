---
id: TASK-1093
title: "fix(hooks): governance \u2014 close the gaps that let agents skip the Scrumban task workflow"
swimlane: core
kind: bug
epic: workflow-enforcement
labels: [governance, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-11-23
started: 2026-11-23
completed: 2026-11-23
agent_session: ses-claude-20261107-135839-5342
depends_on: []
blocked_by: []
references: []
---
# TASK-1093: fix(hooks): governance — close the gaps that let agents skip the Scrumban task workflow

**Outcome (one sentence):** A code edit in a coding-os project always runs under an in_progress task bound to the session, unless the turn is explicitly trivial; prompt wording, fake task anchors and unrecordable gates can no longer switch enforcement off.

## Read First
- docs/governance/task-lifecycle.md
- docs/engineering/task-mode-matrix.md
- src/core/hooks/registry.yaml

## Repro Steps
1. In a coding-os project, send an implementation prompt, let the agent propose a plan, then reply with a short "ok, do it" (classified `chore`).
2. The agent edits code with no task, or records `CLEAR 1`, or writes a `.doc-anchor` of `task:<any old TASK>`; in a Go/Swift project no task is asked for at all.
Expected: no code edit lands without an `in_progress` task bound to the session (bar an explicitly trivial turn).
Actual: chore/query/adhoc modes exempt enforce-task-start; CLEAR 1 bypasses even for implementation prompts; any task id unlocks doc-anchor; only .py/.ts/.tsx are checked; cos_classify_prompt cannot record the gate (recorded=false).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** any task-mode but `system`, **When** a file whose extension is in `.coding-os.yaml` `code_extensions` is edited with no `in_progress` task bound to the panel, **Then** enforce-task-start blocks; a `CLEAR 1` gate lets it through only outside `propose-formal`/`gov-required`
- **Given** a `propose-formal` turn, **When** the next prompt classifies as `chore`, **Then** the mode stays `propose-formal`
- **Given** a `.doc-anchor` of `task:<ID>`, **When** ID is not the panel's current task or that task is not `in_progress`, **Then** enforce-doc-anchor blocks
- **Given** a Claude panel, **When** the agent calls `cos_classify_prompt`, **Then** the gate is recorded for that panel (`recorded=true`) and block messages name the tool before `write-state.sh`
- **Given** plain-text Given/When/Then acceptance (one or several), **When** `cos task-create` then `cos task-start` run, **Then** the DoR gate passes without hand-editing; the hot task tools load without ToolSearch
- **Given** a subagent launched while a task is active, **When** it starts, **Then** it receives the task id, title and Read First as context
- **Given** the hook, MCP, CLI and golden suites plus lint, **When** run, **Then** they pass

## Work Log
- 2026-11-23T13:20:00Z — Verified the six reported causes in code: (1) task anchors were never checked against the panel's task; (2) cos_classify_prompt could not see the panel; (3) query/adhoc/chore modes switched enforce-task-start off, a self-written CLEAR 1 bypassed it in every mode, and only .py/.ts/.tsx counted as code; (4) subagents run the same hooks but get no task context; (5) --acceptance kept the last value and plain G/W/T failed DoR, a bug's repro never reached the in_progress preview, and the task tools sat behind ToolSearch. Also found: sync-task-current bound rejected moves and text that merely mentioned a task, used non-existent status names and substring ids, and two block messages advertised CLEAR 1 / a hand-written exploratory marker.
- 2026-11-23T13:20:00Z — Plan: enforce on the action and the board state, never on prompt wording: code edits need this panel's in_progress task (status read from the task file), CLEAR 1 is the only escape and is refused for implementation prompts, short follow-ups keep the implementation mode; reuse existing seams (check-state helpers, the MCP caller injector, SubagentStart, tools/list _meta) instead of new machinery (anti-overengineering, SSOT-first).
- 2026-11-23T13:20:00Z — Verified: new tests/test_hooks_task_gate.py 20 passed; hook suites 72 passed; thinking_os 730 passed; DoR tests 11 passed; make verify-hooks, make lint, docs-lint green; manifest adds only the inject-subagent-task shim; goldens recaptured (also clears the settings.json drift from 12a641bb).
- 2026-11-23 [claude]: Status transitioned to complete via cos task-done.
