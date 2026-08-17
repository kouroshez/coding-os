---
id: TASK-842
title: "Wire the cross-adapter Channel-2 memory-read pointer into the AGENTS.md retrieval fragment"
swimlane: templates
kind: bug
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-07-17
started: 2026-07-17
completed: 2026-07-17
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-842: Wire the cross-adapter Channel-2 memory-read pointer into the AGENTS.md retrieval fragment

**Outcome (one sentence):** Non-Claude adapters (Codex et al.) are told, in their own instructions file, to read the committed .agents/memory/MEMORY.md during Orient — delivering the contract learning-extraction.md already documents ("Other adapters read .agents/memory/MEMORY.md via their instructions file"), which no instructions file actually carried. Claude keeps its symlink auto-load; every runtime now reaches the same versioned cross-session lessons.

## Read First
- docs/engineering/learning-extraction.md
- src/templates/_base/fragments/retrieval-routing.md.tmpl
- tests/golden/codex_django/AGENTS.md
- src/adapters/claude/hooks/ensure-agent-memory-link.sh

## Repro Steps
grep -rn 'agents/memory|MEMORY.md' on all AGENTS.md / CLAUDE.md / template fragments returns nothing: the Channel-2 read pointer documented at learning-extraction.md line 423-424 is not wired into any instructions file. A consumer's Codex reads its AGENTS.md (no pointer), so the committed .agents/memory/MEMORY.md cross-session lessons stay invisible to it — only Claude (which auto-loads via the ~/.claude symlink) benefits.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the base retrieval-routing fragment with the memory module enabled **When** a consumer AGENTS.md is rendered (Codex or Claude) **Then** it contains a directive to read .agents/memory/MEMORY.md as the portable/versioned memory layer.
**Given** the fragment edit **When** the golden fixtures are regenerated **Then** tests/golden/codex_django/AGENTS.md carries the pointer and test_golden_parity passes.
**Given** the four-layer memory model **When** the pointer is added **Then** it does not contradict the DB-backed memory layer — it names .agents/memory/MEMORY.md as the committed mirror of that same layer, not a fifth store.

## Work Log
- 2026-07-17 [claude]: Edit learning-extraction.md
- 2026-07-17 [claude]: commit 90284bd5e3 — fix(templates): wire cross-adapter Channel-2 memory-read pointer into AGENTS.md
- 2026-07-17 [claude]: Verified: retrieval-routing fragment edited; goldens regenerated (make golden-capture, 8 sections); Channel-2 pointer…
