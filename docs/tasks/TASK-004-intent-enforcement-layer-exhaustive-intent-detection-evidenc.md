---
id: TASK-004
title: "Intent enforcement layer — exhaustive-intent detection + evidence verification"
swimlane: core
kind: feature
epic: null
labels: [intent, enforcement, governance, completion-discipline, epic]
status: in_progress
priority: P1
appetite: "5d"
created: 2026-05-17
started: 2026-05-16
completed: null
agent_session: ses-claude-20260516-191012-948f
depends_on: []
blocked_by: []
references: []
---
# TASK-004: Intent enforcement layer — exhaustive-intent detection + evidence verification

**Outcome (one sentence):** Agent reads natural-language exhaustive intent ("", "all", "completely") correctly, writes findings to compaction-resilient artifact file, evidence-verified before "done" claim, auto-reviewer catches gaps. 15 functional groups split into 3 waves. No premature completion.

## Read First
- src/core/hooks/registry.yaml — SSOT for hook registration
- src/core/hooks/nudge-graph-os.sh — proven UserPromptSubmit nudge pattern
- src/core/hooks/cos-env.sh — env helpers (COS_AGENT_DIR, cos_log_hook, cos_read_stdin_bounded, cos_one_shot_override)
- docs/governance/critical-rules.md — Rule 13 envelope, Rule 16 EvidenceBundle, Rule 22 anti-overengineering
- src/core/thinking_os/tools/ — cos_supervise + cos_supervise_record_output target
- docs/engineering/hooks-reference.md — nudge pattern catalogue

## Acceptance (G/W/T) — *this IS the Definition of Done*

**Wave 1 — Foundation**
- **Given** user types prompt containing "", "all", "completely", "exhaustive" with a scope verb (fix/find/audit/migrate)
- **When** UserPromptSubmit fires
- **Then** detect-exhaustive-intent.sh writes `.coding-os/<agent>/.intent.json` with `{kind, exhaustive: true, scope_verbs, detected_at}` AND injects context "Detected exhaustive intent. Evidence required."

**Wave 1 — Vocabulary**
- **Given** new session starts
- **When** SessionStart fires
- **Then** intent-primer.sh injects ≤300 token card listing FA+EN exhaustive vocabulary + behavior rule + reference to docs/engineering/intent-vocabulary.md

**Wave 1 — Compaction Resilience**
- **Given** intent.json exists with exhaustive=true
- **When** agent attempts Edit/Write
- **Then** enforce-audit-artifact.sh blocks unless `docs/tasks/audits/audit-<slug>.md` exists with mandatory header row

**Wave 2 — Evidence Required**
- **Given** task with detected exhaustive intent
- **When** agent calls cos_supervise_record_output
- **Then** EvidenceBundle must include {categories_declared, categories_covered, counts_before, counts_after, gaps_remaining} — rejected if categories_declared ⊄ categories_covered or counts_after > 0

**Wave 2 — Completion Guardian**
- **Given** Stop event for session with intent=exhaustive
- **When** verify-completion-claim.sh runs
- **Then** completion_guardian.py asserts declared ⊆ covered + counts_after=0 + tests_run includes matrix → on fail injects "GAP: [...]" continuation

**Wave 2 — Auto-Reviewer**
- **Given** cos task-done called for task with intent=exhaustive
- **When** transition fires
- **Then** reviewer subagent spawns (Explore, ≤5K tok), re-greps top 3 categories, ABORT if hit found → task auto-reopens

**Wave 3 — Formula + Subagent + Matrix + Learning + UI + CI + Auto-mode** (per groups 2/8/9/11/13/14/15)
- **Given** exhaustive intent ∧ ≥5 categories
- **When** agent edits without prior Agent subagent_type=Explore call in current phase
- **Then** enforce-subagent-delegation.sh blocks

- **Given** declared_done with EvidenceBundle missing counts_after=0
- **When** cos cognition trace-replay runs in CI
- **Then** assertion fails → daily standup surfaces premature-done

## Definition of Done (cross-cutting)
- All 15 groups landed with per-group commits
- `make verify-hooks` green
- `uv run pytest src/core/thinking_os/tests/ tests/test_hooks_*.py tests/test_cli.py -q` green
- `make regen-adapter-templates` clean
- `bash src/adapters/claude/install.sh` clean (dogfood)
- `cos doctor` clean
- `make docs-lint` clean

## Work Log
- 2026-05-17 [claude]: G10 done: docs/engineering/intent-vocabulary.md created. Canonical FA+EN exhaustive vocab table + scope verbs + 6 predic
- 2026-05-17 [claude]: G0 done: SessionStart intent-primer.sh hook + registry entry (cognition/phase P) + regenerated Claude settings template.
- 2026-05-17 [claude]: G1 done: detect-exhaustive-intent.sh + _helpers/extract_intent.py — 20-token sliding window co-occurrence (exhaustive ve
- 2026-05-17 [claude]: G12 done: docs/_meta/audit-checklist-template.md + enforce-audit-artifact.sh (PreToolUse Edit|Write, blocks when exhaust
- 2026-05-17 [claude]: G3 done: ExhaustiveEvidence Pydantic model (10 fields: categories_declared/covered, counts_before/after, files_searched,
- 2026-05-17 [claude]: G4 done: completion_guardian.py (audit-row count + EvidenceBundle predicate validation, dataclass GuardResult) + verify-
- 2026-05-17 [claude]: G5 done: prevent-premature-done.sh Stop hook — per-session debounced nudge asking agent to name 3 deliberately-excluded
- 2026-05-17 [claude]: G6 done: cos_task_move extended with reviewer_hint payload — when to=complete + intent.exhaustive=true + active audit-*.
- 2026-05-17 [claude]: G7 done: enforce-count-grounding.sh — PreToolUse Edit|Write nudge for grep-before/grep-after discipline. Skip conditions
