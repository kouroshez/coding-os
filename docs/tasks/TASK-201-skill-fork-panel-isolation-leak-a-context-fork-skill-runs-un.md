---
id: TASK-201
title: "Skill-fork panel isolation leak: a context:fork skill runs under a sibling panel and mutates its task"
swimlane: core
kind: bug
epic: agent-hub
labels: [ready]
status: icebox
priority: P1
appetite: "1d"
created: 2026-06-06
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-201: Skill-fork panel isolation leak: a context:fork skill runs under a sibling panel and mutates its task

**Outcome (one sentence):** A skill with `context: fork` (e.g. `clean-code`), when invoked by panel A, runs under panel A's `COS_PANEL_DIR` and reads panel A's `.task-current` — never a sibling panel's — so a forked skill can never read or mutate another panel's active task.

## Read First
- docs/engineering/state-files.md (per-panel scope + `cos_panel_upgrade_from_payload`)
- src/core/hooks/cos-env.sh (panel/session resolution — likely fix site)
- src/core/hooks/session-context.sh (panel-id seeding from stdin `session_id`)
- docs/engineering/agent-hub-orchestration.md (§1 id-spaces, F2 attribution fix)

## Repro Steps
1. Two concurrent Claude panels of the same agent on this repo: panel A (`ses=…db30`) and panel B (`ses=…0b9f`), B has `.task-current=TASK-196` (in_progress).
2. From panel A, invoke the `clean-code` skill (frontmatter `context: fork`) — a normal pre-edit skill load.
3. Observed: the fork executed under **panel B** (`ses=840b9ff`), read B's `.task-current` (TASK-196), did B's work, and drove TASK-196 `in_progress → testing → complete` + submitted an EvidenceBundle — all attributed to B, triggered by A's invocation.
4. Expected: the fork runs under panel A, sees A's `.task-current` (TASK-197), and never touches TASK-196.

## Root-cause hypothesis
Same class as F2 (TASK-167). A `context: fork` skill spawns a subagent that sources `cos-env.sh` and resolves its panel. When the fork does not carry panel A's `session_id`, the resolver falls back to a shared/agent-level pointer (e.g. `$COS_AGENT_DIR/.active-session` or the last-written `session-id`) which the most-recently-active sibling panel (B) wrote — so the fork lands in B's `COS_PANEL_DIR`. The transparency-banner accuracy contract already mandates STRICT panel-scoped reads with no `$COS_AGENT_DIR` fallback; the fork path appears to bypass that.

## Proposed fix direction (not yet implemented)
- Propagate the invoking panel's `COS_PANEL_ID` into the forked subagent's environment so `cos-env.sh` resolves the parent panel deterministically; OR
- Make the fork's panel resolution STRICT (panel-scoped session-id only, no agent-level `.active-session` fallback) — mirroring the `_read_state` hardening in transparency-banner.md.
- Add a regression test: simulate two panels, fork from A, assert the fork's resolved `COS_PANEL_DIR` == A's (never B's).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** two concurrent same-agent panels A and B with distinct `.task-current`
- **When** panel A invokes a `context: fork` skill
- **Then** the fork resolves panel A's `COS_PANEL_DIR`, reads A's `.task-current`, and cannot read or mutate B's task/markers; a regression test asserts the resolved panel identity; `make verify-hooks` green.

## ⚠️ Why this is filed, not fixed in this session
The likely fix site (`cos-env.sh` / panel resolution) currently carries **uncommitted changes from the sibling session** (TASK-196 added latency instrumentation to `cos-env.sh`). Editing it now would sweep or collide with that peer's WIP — the exact failure mode this very epic exists to prevent. Pick this up once `cos-env.sh` is committed/clean.

## Work Log
