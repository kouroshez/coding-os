---
id: TASK-201
title: "Skill-fork panel isolation leak: a context:fork skill runs under a sibling panel and mutates its task"
swimlane: core
kind: bug
epic: agent-hub
labels: [ready]
status: complete
priority: P1
appetite: "1d"
created: 2026-06-06
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-201: Skill-fork panel isolation leak: a context:fork skill runs under a sibling panel and mutates its task

**Outcome (one sentence):** A `context: fork` skill (e.g. `clean-code`) invoked by panel A must run under panel A's identity — never a sibling panel's. Observed: panel db30 invoking clean-code produced a forked execution under panel **840b9ff** that drove that panel's task (TASK-196) to complete.

## Read First
- src/core/hooks/cos-env.sh (`_cos_resolve_panel_id`, lines ~133-169 + strict session-id read ~236)
- docs/engineering/state-files.md (per-panel scope)
- docs/engineering/agent-hub-orchestration.md (§1 id-spaces, F2)

## Repro Steps
1. Two concurrent same-agent panels: A (`ses=…db30`), B (`ses=…0b9f`, `.task-current=TASK-196`).
2. From A, invoke `clean-code` (frontmatter `context: fork`).
3. Observed: a forked execution ran under B's identity (banner `ses=840b9ff`), read B's `.task-current`, did B's work, drove TASK-196 → complete. No data corruption (B's work was correct + attributed to B), but A's action mutated B's panel.

## ⚠️ Investigation update (2026-06-06) — corrected root cause
Read `cos-env.sh::_cos_resolve_panel_id`: `COS_PANEL_ID` resolves from a **per-process env var** (`CLAUDE_CODE_SESSION_ID` / `CURSOR_SESSION_ID` / `CODEX_SESSION_ID`, else a (PPID,agent) hash) — NOT from a shared/last-writer pointer. The session-id read is already STRICT panel-private with NO `$COS_AGENT_DIR` fallback (explicit cross-panel-leak guard). **So cos-env.sh is correct; my first hypothesis (shared-pointer leak) was wrong.**

The fork landed on B's identity only if its `CLAUDE_CODE_SESSION_ID` was B's — i.e. the **Claude harness/SDK fed the forked skill the wrong (sibling) session id**, or the harness routed B's concurrent skill result to A's call. Either way the defect is **upstream of coding-os**, not in repo code.

**Consequence:** there is NO safe in-repo fix in `cos-env.sh` — editing the highest-blast-radius file (sourced by every hook, every session, every project) to "fix" correct code would be reckless. coding-os cannot know a fork's intended parent without a harness-supplied signal it isn't given.

## Disposition
- **Not an in-repo code bug.** cos-env.sh panel resolution is correct.
- Possible defensive options IF the harness ever exposes a parent-session signal to forks: have the fork re-assert `COS_PANEL_ID` from that signal. Until then, no action.
- Recommend: report upstream (Claude Agent SDK / Code) that a `context: fork` skill can execute under a sibling session's identity; and prefer non-fork (`context: inline`) for skills that read/write panel state.

## Acceptance (G/W/T)
- **Given** this investigation
- **When** a maintainer reviews TASK-201
- **Then** the record states cos-env.sh is correct and the leak is upstream; no high-blast-radius edit is made on a hypothesis; the upstream report / `context:` recommendation is captured. (Reopen for a code fix ONLY if the harness later exposes a parent-session signal.)

## Related
Same observable family as F2 (TASK-167) and [[TASK-205]], but DIFFERENT layer — F2/205 are in-repo; this one is upstream.

## Work Log
- 2026-06-06 [claude]: Status transitioned to complete via cos task-done.
