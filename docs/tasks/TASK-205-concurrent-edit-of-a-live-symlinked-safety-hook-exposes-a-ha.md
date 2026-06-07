---
id: TASK-205
title: "Concurrent edit of a live-symlinked safety hook exposes a half-written wrongly-blocking state to every session"
swimlane: core
kind: chore
epic: agent-hub
labels: [ready]
status: complete
priority: P2
appetite: "1d"
created: 2026-06-06
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-205: Concurrent edit of a live-symlinked safety hook exposes a half-written wrongly-blocking state to every session

**Outcome (one sentence):** A session editing a live-symlinked `block-*.sh` safety hook across turns must not make other concurrent sessions execute an inconsistent mid-edit version on every tool call (today they do — a peer's in-progress edit transiently made this session's harmless `ls` wrongly BLOCK).

## Read First
- src/core/rules/git-workflow.md (§ concurrent sessions)
- docs/engineering/state-files.md (per-session isolation model)
- src/core/hooks/registry.yaml
- CLAUDE.md (Modularity Map — "hooks → ALL consumer projects via live symlinks")

## Repro
1. Session A (this one) and session B both live. B edits `src/core/hooks/block-dangerous-commands.sh` across several turns (TASK-196 fail-closed hardening).
2. A runs a harmless `ls src/core/thinking_os/agents` (and `grep`, `write-state.sh .task-current`).
3. Observed: A's commands BLOCKED with "recursive rm targeting a critical path" — a wrong verdict, because A executed B's half-written hook (hooks are live symlinks → instant propagation, including inconsistent intermediate states).
4. Self-healed once B's edit settled. The committed hook + `check_dangerous_rm.py` + `test_block_dangerous_commands.py` are all correct (verified) — the defect is exposure of the mid-edit state, not the code.

## Root cause
Deliberate live-symlink design (CLAUDE.md: hooks propagate with "none" rebuild) trades instant propagation for exposure to half-written edits. A multi-turn edit of a `block-*` hook leaves it briefly syntactically-valid-but-semantically-wrong, and every sibling session runs it.

## Proposed mitigations (pick by cost/benefit — likely (a))
- **(a) Process / lightweight (recommended):** edit safety hooks atomically (single Edit, or write-to-temp → `bash -n` + `make verify-hooks` → swap); never leave a `block-*` hook half-edited across turns. Document this in git-workflow.md § concurrent sessions. Cheapest; sufficient for single-user-multi-session.
- **(b) Architectural (deferred — likely over-engineering):** sessions execute a committed/staged snapshot of hooks instead of the live working tree. Removes the hazard but breaks the "instant propagation, no rebuild" property and adds a sync step.

## Acceptance (G/W/T)
- **Given** a session is mid-editing a `block-*` safety hook
- **When** another concurrent session runs a legitimate command
- **Then** the documented protocol (atomic edit + verify-before-yield) is in git-workflow.md, so a half-written safety hook is never the live version across a turn boundary; `make docs-lint` green. (Snapshot isolation explicitly deferred with rationale.)

## Related
Same family as [[TASK-201]] (skill-fork panel leak) and F2 (TASK-167 MCP attribution) — all session-isolation gaps in the multi-agent kernel. See docs/engineering/agent-hub-orchestration.md.

## Work Log
- 2026-06-06 [claude]: Added atomic-edit + verify-before-yield protocol for live-symlinked block-*/enforce-* safety hooks to git-workflow.md §
- 2026-06-06 [claude]: committed c139c782: src/core/rules/git-workflow.md
