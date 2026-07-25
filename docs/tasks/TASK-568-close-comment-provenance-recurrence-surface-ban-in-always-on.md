---
id: TASK-568
title: "Close comment-provenance recurrence: surface ban in always-on Rule 12 + de-contradict block-bad-patterns TODO rule"
swimlane: core
kind: bug
epic: null
labels: [governance, docs-update, comments, discipline, hooks, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-25
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-568: Close comment-provenance recurrence: surface ban in always-on Rule 12 + de-contradict block-bad-patterns TODO rule

**Outcome (one sentence):** Stop comment-spam recurrence (TASK-NNN provenance leaking into committed comments — e.g. commit ed214339 added '(TASK-565)' to test files) by closing the two diagnosis-confirmed root causes with the smallest cross-runtime, behavior-preserving change: (R3) the provenance ban is never in context on test-only edit sessions because enforce-skill.sh / enforce-doc-anchor.sh short-circuit on *test* paths and clean-code is never a block-required primary, so the ban (clean-code §4) never loads; (X) block-bad-patterns.sh actively mandates TASK-### inside TODO comments, training the exact behavior §4 forbids. Fix = (1) add the concrete forbidden-provenance tokens to the always-on AGENTS.md Rule 12 one-liner; (2) reword block-bad-patterns.sh framing/message only (grep behavior unchanged).

## Read First
- AGENTS.md
- src/core/hooks/block-bad-patterns.sh
- src/core/skills/clean-code/SKILL.md
- docs/governance/critical-rules.md

## Repro Steps
ed214339 committed '(TASK-565)' provenance comments to tests/test_hooks.py:664,681 and tests/test_cli.py:3543. Root causes: enforce-skill.sh:21-24 exits 0 on any *test* path BEFORE any skill check; clean-code (home of §4 No-Provenance ban) is never a PRIMARY in skill-enforcement.md so it is never block-required; the always-on AGENTS.md Rule 12 one-liner lacks the forbidden-token list; block-bad-patterns.sh:104-105 requires TASK-### present to pass its TODO check, contradicting clean-code §4 and Rule 12.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a session editing only test files (enforce-skill.sh:21-24 and enforce-doc-anchor.sh both skip *test*), **When** the agent reads the always-on AGENTS.md, **Then** the Rule 12 row names the concrete forbidden-provenance tokens (TASK-NNN / Phase-N / P5:) so the ban is in context with zero Skill load.
- **Given** block-bad-patterns.sh blocks a bare TODO, **When** the agent reads the BLOCK message, **Then** it directs to cos task-create and frames a task-ref as a transient TODO-marker to remove before commit (never provenance in an explanatory comment) — while the grep/exit behavior stays UNCHANGED.
- **Given** the safety-hook edit, **When** verification runs, **Then** make verify-hooks passes, AGENTS.md stays under 120 lines, and no existing TestBlockBadPatterns / hook test regresses.

## Work Log
- 2026-06-25 [claude]: Edit AGENTS.md
- 2026-06-25 [claude]: Edit block-bad-patterns.sh
- 2026-06-25 [claude]: commit 7971e51a50 — fix(governance): put comment-provenance ban in always-on Rule 12 + de-contradict TODO hook
- 2026-06-25 [claude]: Multi-agent diagnosis confirmed R3 (test-only edits bypass enforce-skill.sh:21-24 + enforce-doc-anchor; clean-code…
