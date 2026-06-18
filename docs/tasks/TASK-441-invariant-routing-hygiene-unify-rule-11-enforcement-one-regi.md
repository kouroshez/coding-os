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
agent_session: ses-claude-20260617-183518-6ce2
depends_on: [TASK-438]
blocked_by: []
references: []
---
# TASK-441: Invariant + routing hygiene: unify Rule-11 enforcement (one registry read), fix model-routing tier-vs-id footgun, add bash -n self-check for safety hooks

**Outcome (one sentence):** Rule-11 is enforced by ONE narrowed registry-derived source instead of three divergent sets, model routing can never forward a tier name as an SDK id (and core stops self-breaching Rule-11), and a half-saved safety hook fails OPEN at install/CI instead of fail-CLOSED across every live-symlinked Claude session. Closes audit R10+R11+R14 + new findings F6+F12+F13 (+F16 flagged).

## Read First
- src/core/scripts/check_hardcoded_literals.py  (discover_literals — now the documented single source)
- tests/test_no_hardcoded_stacks.py  (frozen 6-item FORBIDDEN_LITERALS)
- src/core/thinking_os/routing.py  (DEFAULT_MODELS / DEFAULT_SKILLS literals + success-only ranker)
- src/adapters/claude/adapter.yaml  (models — concrete SDK ids)
- src/core/scripts/install-adapter.sh  (symlink site — no bash -n gate)

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a hardcoded stack/adapter literal in src/cli/** **When** test_no_hardcoded_stacks runs **Then** it imports the SAME discover_literals() the hook uses — BUT discover_literals must first be NARROWED to stack/adapter ids only (drop the `skills` loop) and must not false-positive on ambiguous short ids. EVIDENCE (this session): raw discover_literals() raises 30 false positives on cli/*.py — `thinking_os`/`observability` (skill names) on path components + dict keys, and `meta`/`go`/`python`/`fastapi` (short ids) on `.get("meta")`, language maps, UI text. So: drop skills; for ambiguous ids require an assignment/value context (not a dict key / path segment) or move the language map to a yaml data file; then unify test↔checker. The false 'mirrors' docstring was already corrected (commit 3034a454, TASK-445).

**Given** cos_route_model on a cold-start project (data_points==0) **When** the result is forwarded to a dispatch tool **Then** it is a real SDK id resolved by the ADAPTER from adapter.yaml::models (claude-sdk.md:191-192 already decided the adapter owns alias→id), never a bare tier like 'sonnet' (F6/R10). Fix the tier-4 gate (cognition.py:1214) to gate on confidence/model_stats, not data_points>0, to honor claude-sdk.md:188.

**Given** model-routing.md states 'no model id literal here' **When** routing.py is inspected **Then** DEFAULT_MODELS (bare tiers) and DEFAULT_SKILLS (python-django/nextjs-react/'bash-linux' stale) are moved to adapter.yaml-driven data — closing the core Rule-11 self-breach the cli-scoped enforcer cannot see (F13).

**Given** a block-*/enforce-* safety hook saved mid-edit with a syntax error **When** it would run **Then** it fails OPEN — Claude has NO dispatcher (settings.template.json calls each hook directly; rc=2 = BLOCK every tool call), so the fix is an install/CI `bash -n` gate that refuses to symlink a syntax-broken hook (NOT the Codex-only dispatcher self-check originally proposed) (F5/R14 re-scoped).

**Given** success-only routing (F16, flag-only here) **When** scoped **Then** note: ranker ignores cost so it converges on always-Opus, and task_outcomes.model is NULL in 359/384 rows — the self-driving-routing data foundation is starved; defer the cost-aware ranker + model-population to a future routing task, DELETE routing_weights now (see TASK-440 delete pass).

**Given** these changes **When** make verify-hooks + test_no_hardcoded_stacks + the routing tests run **Then** they pass.

## Work Log
- 2026-06-18 [claude]: Edit install-adapter.sh
- 2026-06-18 [claude]: Edit install-adapter.sh
- 2026-06-18 [claude]: commit 574765732a — feat(modularity): install-time bash -n gate — never link a syntax-broken hook (R14/F5)
- 2026-06-18 [claude]: Edit sdk_dispatcher.py
- 2026-06-18 [claude]: Edit sdk_dispatcher.py
- 2026-06-18 [claude]: Edit sdk_dispatcher.py
- 2026-06-18 [claude]: Edit sdk_dispatcher.py
- 2026-06-18 [claude]: Edit sdk_dispatcher.py
- 2026-06-18 [claude]: Edit sdk_dispatcher.py
- 2026-06-18 [claude]: Edit test_claude_dispatcher_options.py
- 2026-06-18 [claude]: commit 6c4c531aab — feat(modularity): adapter resolves model tier aliases to concrete SDK ids (R10/F6)
- 2026-06-18 [claude]: F5 + F6 LANDED + verified + pushed. F5 (install-time bash -n gate, install-adapter.sh) + finding: CI ALREADY has bash…
- 2026-06-18 [claude]: commit 24e7d7a04b — chore(tasks): TASK-441 work-log — F5+F6 landed/verified; F12/F13 design forks parked
- 2026-06-18 [claude]: Edit routing.py
- 2026-06-18 [claude]: commit 11a60dd4d7 — fix(modularity): route_skill cold-start no longer suggests the dangling 'bash-linux' skill (F13)
- 2026-06-18 [claude]: F13 LANDED (11a60dd4): route_skill cold-start no longer suggests the dangling non-existent 'bash-linux' skill (→…
