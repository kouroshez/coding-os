---
id: TASK-497
title: "Guarantee the Constitution slice re-inherits every session (non-decaying) + assert presence in cos_health"
swimlane: "thinking_os"
kind: feature
epic: teach-why-alignment
labels: [teach-why, health, persistence, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-21
started: 2026-06-20
completed: 2026-06-20
agent_session: ses-system-auto-archive
depends_on: [TASK-491]
blocked_by: []
references: []
---
# TASK-497: Guarantee the Constitution slice re-inherits every session (non-decaying) + assert presence in cos_health

**Outcome (one sentence):** Guidance that lives only in a doc the agent might read is the "merely imposed" value the article calls brittle. coding-os's killer feature is cross-session persistence (digest re-inheritance, decaying memory) — but values are NOT currently guaranteed to re-inherit, and memory DECAYS low-confidence items (correct for patterns, catastrophic for character). Pin the compressed constitution slice into the GUARANTEED SessionStart inheritance and mark it non-decaying / not eligible for memory GC, so it re-inherits identically every startup/resume (the "character does not decay" invariant — the runtime analogue of the article's "alignment persists through RL"). Add one assertion to the existing cos_health (or startup self-check) that the slice is present; treat absence like a dangling-symlink repair. Reuse the digest-suppression-on-compact logic; inject only the compressed slice (avoid the multi-thousand-token compaction wall). No new persistence subsystem.

## Read First
- src/core/hooks/session-context.sh
- docs/engineering/state-files.md
- src/core/rules/memory.md
- docs/governance/constitution.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** any startup/resume SessionStart, **When** context is inherited, **Then** the constitution slice is present and is excluded from memory decay/GC.
- **Given** cos_health, **When** run, **Then** it asserts the constitution slice is present and reports a clear failure with a repair hint if absent.
- **Given** source=compact, **When** session-context.sh runs, **Then** the slice is NOT re-dumped (reuses existing suppression).
- **Given** the change set, **When** verifying, **Then** `uv run --extra rag pytest src/core/thinking_os/tests/ -q -m 'not slow'` + `make verify-hooks` + `python src/core/thinking_os/server.py --test` are GREEN.

## Work Log
- 2026-06-21 [claude]: Edit server.py
- 2026-06-21 [claude]: Edit constitution.md
- 2026-06-21 [claude]: commit 6d568944f6 — feat(thinking_os): assert Constitution-slice presence in cos_health (non-decaying values invariant)
- 2026-06-21 [claude]: cos_health (server.py thinking_os_health) now emits a constitution block {present, slice_markers_ok, non_decaying,…
