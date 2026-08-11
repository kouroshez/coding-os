---
id: TASK-852
title: "Bounded skill/rule edit-patch drafts staged behind the held-out gate + governance adopt"
swimlane: core
kind: feature
epic: null
labels: [learning-loop, skill-evolution, keep]
status: archive
priority: P2
appetite: 1d
created: 2026-07-24
started: null
completed: null
agent_session: ses-claude-20260807-224955-abc1
depends_on: [TASK-851]
blocked_by: []
references: []
---
# TASK-852: Bounded skill/rule edit-patch drafts staged behind the held-out gate + governance adopt

**Outcome (one sentence):** Extend generalize_lessons/cos_promote to emit learning_rate-clipped add/delete/replace patches on SKILL.md / rule.md PROSE bodies (never front-matter), staged as diffs in .coding-os/memory/drafts/, applied only behind the held-out gate (TASK-851) AND a human-opened governance/docs-update task — never bypassing block-protected-files (hardened in TASK-849). Add a draft-expiry policy so unadopted drafts decay instead of piling up. Target SKILL.md bodies + the 8 hand-written rule .md + stack.yaml source rows, never the derived skill-enforcement.md/dimension-registry.md. See ADR-0016.

## Read First
- docs/architecture/adr/0016-gated-skill-evolution-roadmap-extend-not-build.md
- src/core/thinking_os/tools/learning.py
- src/core/hooks/block-protected-files.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
Given a validated lesson cluster, When the distiller proposes a skill/rule change, Then it writes a bounded (<= learning_rate edits) prose-only diff to .coding-os/memory/drafts/ and never touches the file directly. Given a staged draft, When no governance/docs-update task adopts it within the expiry window, Then it decays/archives. Given an attempt to apply a draft, Then it passes through block-protected-files (governance marker required), never around it.

## Work Log
- 2026-08-02 [claude]: Triage 2026-08-02: deliberately staying keep — stage 3 of ADR-0016; gated behind the TASK-851 feasibility verdict,…
