---
id: TASK-059
title: "Workflow-integrity hardening: close tool-bypass back doors + semantic state surface"
swimlane: core
kind: feature
epic: workflow-integrity
labels: [enforcement, hooks, guardian, dx]
status: archive
priority: P1
appetite: "1d"
created: 2026-06-02
started: 2026-06-02
completed: 2026-06-02
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-059: Workflow-integrity hardening: close tool-bypass back doors + semantic state surface

**Outcome (one sentence):** Agents can no longer bypass the cos_* surface for task/audit lifecycle or discovery. Hand-Edit of task/audit status is blocked (hook); the completion guardian cross-checks evidence against formula_dispatches (not the editable checkbox); agents are steered to cos task-show/cos_task_search and to semantic state ops instead of raw write-state.sh; dead/duplicate surface removed. All backward-compatible, all verified.

## Read First
- docs/governance/critical-rules.md
- src/core/hooks/registry.yaml
- src/core/thinking_os/completion_guardian.py
- src/core/hooks/validate-task-frontmatter.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an agent hand-Edits `status:`/checkbox in a `docs/tasks/**/*.md` (incl. `audits/`), **When** the PreToolUse hook fires, **Then** it BLOCKS with the exact `cos_task_move`/`cos task-done`/`cos_supervise_record_output` command (allow-listed for governance/docs-update tasks + `COS_ALLOW_TASK_EDIT=1`).
- **Given** an audit checkbox claims evidence was submitted, **When** the completion guardian runs at Stop, **Then** it cross-checks a real `formula_dispatches` row for the session and reports a gap if absent — never relaxing existing gaps.
- **Given** a session, **When** the agent needs gate/task-current/anchor, **Then** semantic ops (`cos_classify_prompt`, `cos task-start`, `cos_doc_anchor_set`) write the panel-correct marker internally; docs/rules no longer teach raw `write-state.sh`; `cos task-show` is reachable as an MCP tool; task-discovery is nudged.
- **Given** the cleanup, **When** the surface is audited, **Then** dead/duplicate surface (`cos_routing_drift`, `cos skills-list`, `cos web`) is resolved and `cos_audit_log_record` auto-fires via a capture hook.
- **Then** every changed layer passes its Verification-Matrix command (verify-hooks, thinking_os pytest + MCP self-test, board_os tests, cli tests, adapter parity, docs-lint) and the dogfood re-render is clean.

## Work Log
- 2026-06-02 [claude]: Shipped 9 fixes: cos_task_show MCP tool; enforce-task-transition hook (blocks status/checkbox hand-edits incl audits/);
- 2026-06-02 [claude]: Status transitioned to complete via cos task-done.
