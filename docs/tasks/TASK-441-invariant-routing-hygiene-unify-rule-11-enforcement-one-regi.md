---
id: TASK-441
title: "Invariant + routing hygiene: unify Rule-11 enforcement (one registry read), fix model-routing tier-vs-id footgun, add bash -n self-check for safety hooks"
swimlane: infra
kind: refactor
epic: null
labels: [modularity, rule-11, model-routing, hooks, audit-2026-06, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-16
started: 2026-06-16
completed: null
agent_session: ses-803-0b9f
depends_on: [TASK-438]
blocked_by: []
references: []
---
# TASK-441: Invariant + routing hygiene: unify Rule-11 enforcement (one registry read), fix model-routing tier-vs-id footgun, add bash -n self-check for safety hooks

**Outcome (one sentence):** The data-driven invariant (Rule 11) is enforced by ONE registry-derived source instead of three divergent sets, model routing can never forward a tier name as an SDK model id, and a half-saved safety hook fails open instead of breaking enforcement across every live-symlinked session. Closes audit R10+R11+R14 (problem-tree Branch C + blast-radius hardening).

## Read First
- src/core/hooks/block-hardcoded-literals.sh
- tests/test_no_hardcoded_stacks.py
- src/core/rules/model-routing.md
- src/adapters/claude/adapter.yaml
- src/core/hooks/registry.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a hardcoded stack/adapter literal committed to src/cli/** **When** test_no_hardcoded_stacks runs in CI **Then** it fails using the SAME discover_literals() registry read as the live hook (no frozen divergent set); the hook is narrowed to stack/adapter IDs (no false-positive on path components / skill names) and the language map moves to a yaml data file.

**Given** cos_route_model on a cold-start project (data_points==0) **When** the result is forwarded to a dispatch tool **Then** the model is a real SDK id from adapter.yaml::models (tier returned as a separate field from a concrete fallback id), never a bare tier name like 'sonnet'.

**Given** a block-*/enforce-* hook saved mid-edit with a syntax error **When** PreToolUse fires **Then** the dispatcher's bash -n self-check makes it fail OPEN (warn) rather than crashing the pipeline for every concurrent session/consumer.

**Given** these changes **When** make verify-hooks + the relevant matrix tests run **Then** they pass.

## Work Log
- 2026-06-16 [claude]: Edit test_board_coherence.py
- 2026-06-16 [claude]: Edit test_board_coherence.py
