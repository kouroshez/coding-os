---
id: TASK-620
title: "Reliability test infra: multi-project fixture + concurrency stress harness + close the mock-satisfiable DoD verify gate"
swimlane: infra
kind: chore
epic: git-foundation-hardening
labels: [pr-mode, testing, reliability, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-27
started: 2026-06-27
completed: 2026-06-27
agent_session: ses-claude-20260625-235014-c028
depends_on: []
blocked_by: []
references: []
---
# TASK-620: Reliability test infra: multi-project fixture + concurrency stress harness + close the mock-satisfiable DoD verify gate

**Outcome (one sentence):** Raise the test floor that lets recurring bug classes ship: add a multi-project isolation fixture (≥2 project roots, each its OWN `.coding-os/`, driven via per-project `COS_PROJECT_ROOT`) that proves settings/state never clobber across projects (the C1/C2 Config→Git drift classes), a bounded concurrency stress test, and tamper-resistance for the DoD verify gate — keyed to honest, code-verified scope (the gate reads `.last-verify.json` BY DESIGN, so "close mock-satisfiable" means make a forged record not satisfy it, or explicitly accept the design).

## Read First
- tests/test_cli.py
- tests/test_hub_settings_git.py
- src/core/web/routes/settings.py
- src/core/board_os/transition_gates_cli.py

## Repro Steps
Workflow whdjyvqjq + review (agent: FLAWED — no acceptance, ambiguous scope). Verified: TestCosPr fixture is single-project (one tmp repo); settings.py:44-56 already routes per-project via current_project_root() (so isolation is testable but UNTESTED — the C1 clobber / C2 drop classes hide); the DoD gate `_verify_state()` (transition_gates_cli.py:77-90) reads `.last-verify.json` from disk — trivially forgeable by a test/agent writing a fake PASS, which is the real "mock-satisfiable" gap (NOT that tests can mock it for flexibility).

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** two project roots A and B each with their own `.coding-os/`, **When** settings are saved for A (e.g. autonomy_level=auto_merge) while B is draft, **Then** the multi-project fixture proves B's hub-settings.json is byte-untouched and unknown sections survive (C1/C2 regression). **Given** N=5 agents × ~10 iterations running open/submit/reap concurrently (fixed-seed jitter, <30s, fcntl present), **When** the stress test runs, **Then** it asserts zero worktree clobber, zero double-reap, zero orphan in the cleanup ledger, no lost commit. **Given** a task attempting testing→complete with only a FORGED `.last-verify.json` (no real matrix run on the current tree), **When** the transition is evaluated, **Then** it is BLOCKED — achieved by binding the verify record to git_head+dirty_digest AND the matched suite (reject a record whose suite/tree doesn't match the change), OR, if that is judged out of scope, the task explicitly DOCUMENTS the gate as defense-in-depth-only and removes this leg. Verify: `uv run pytest tests/test_cli.py tests/test_hub_settings_git.py -q` + the new multi-project + concurrency tests green.

## Work Log
- 2026-06-28 [claude]: 3 deliverables: (1) multi-project C1 no-clobber test (scoped save to A leaves B byte-identical + C2 unknown-section…
