---
id: TASK-119
title: "Ship regen_doc_index to consumers + fix dead hook candidate path — 00-index regen is a no-op in every cos init"
swimlane: core
kind: bug
epic: doc-system
labels: [docs-system, dogfood, graph, audit-d7-f3, overlap-TASK-113, ready]
status: complete
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-119: Ship regen_doc_index to consumers + fix dead hook candidate path — 00-index regen is a no-op in every cos init

**Outcome (one sentence):** auto-regen-doc-index.sh resolves its generator inside a consumer project (preferably by calling a shipped CLI surface e.g. cos docs-index --regen-nav <dir> rather than scaffolding a loose script), so docs/<dir>/00-index.md freshness works in every organism, not just the meta-repo dogfood path. Also fixes the relative-path exit-127 invocation breakage and the omitted Nav line.

## Read First
- src/core/hooks/auto-regen-doc-index.sh
- src/scripts/regen_doc_index.py
- src/core/scaffold_manifest.json

## Repro Steps
1. In a scaffolded consumer, write a `docs/<dir>/*.md` so the PostToolUse `auto-regen-doc-index.sh` fires.
2. Check whether `docs/<dir>/00-index.md` regenerates.
Expected: 00-index regenerates (hook resolves the generator).
Actual (pre-fix): no-op / exit-127 — the `$(dirname "$0")/../../scripts/regen_doc_index.py` relative path never resolved under the symlinked install, so the generator never ran.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a consumer project whose `.claude/hooks/auto-regen-doc-index.sh` is live-symlinked to the meta-repo
- **When** a doc under `docs/<dir>/` is written and the PostToolUse hook fires
- **Then** the hook resolves the generator via its symlink chain (`HOOK_REAL_DIR/../../scripts/regen_doc_index.py`, commit 5b299c24) — the broken relative-path candidate is gone — and regenerates `docs/<dir>/00-index.md` including the `> Nav:` breadcrumb (added under TASK-130).

The Outcome's "preferred CLI surface" (`cos docs-index --regen-nav`) is satisfied by this symlink-resolution path, which IS the Outcome's explicit "rather than scaffolding a loose script" alternative — so no dedicated CLI wrapper is added (anti-overengineering: the goal — 00-index freshness in every organism without a vendored script — is met). Verified: generator resolves via `../../scripts/regen_doc_index.py` and emits a valid Nav-bearing index (TASK-130 smoke).

## Work Log
- 2026-06-06 [claude]: Status transitioned to complete via cos task-done.
