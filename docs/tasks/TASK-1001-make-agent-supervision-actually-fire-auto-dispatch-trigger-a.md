---
id: TASK-1001
title: "Make agent supervision actually fire \u2014 auto dispatch trigger, always-on banner, doctor check"
swimlane: core
kind: bug
epic: null
labels: [governance, docs-update, supervision, hooks, ready]
status: in_progress
priority: P1
appetite: 2d
created: 2026-08-17
started: 2026-08-17
completed: null
agent_session: ses-claude-20260816-230826-9ffd
depends_on: []
blocked_by: []
references: []
---
# TASK-1001: Make agent supervision actually fire — auto dispatch trigger, always-on banner, doctor check

**Outcome (one sentence):** `model_routing.enabled=true` actually fires — a hook resolves and surfaces the role route for COMPLICATED+ gates, the transparency banner is present in every task mode under every adapter and names the routing adapter/model, the banner never reports another panel's stale role chain, `cos doctor` reports supervision health, and supervise+dispatch carry executable tests.

## Read First
- src/core/rules/model-routing.md
- src/core/rules/transparency-banner.md
- docs/engineering/agent-supervision.md
- docs/engineering/dispatcher-contract.md
- src/core/hooks/session-context.sh
- src/core/hooks/auto-compose-roles.sh

## Repro Steps
1. `jq '.model_routing' .coding-os/hub-settings.json` → `enabled=true` since 2026-08-12.
2. `sqlite3 .coding-os/coding-os.db "SELECT adapter, model, ts FROM formula_dispatches ORDER BY ts DESC LIMIT 6"` → `adapter`/`model` empty in all 43 rows; newest non-fixture row is 2026-06-07.
3. `grep -rn dispatch_formula_run src/core/hooks/` → no hook calls it, so nothing auto-fires.
4. Banner in `query` mode omits every cognitive field and has no adapter/model field at all (`session-context.sh:701`).
5. `session-context.sh:502-505` falls back to `$COS_AGENT_DIR/.roles`, so the banner showed a 2026-08-11 chain inside a fresh panel — contradicting `transparency-banner.md` "STRICTLY panel-scoped (no `$COS_AGENT_DIR` fallback)".

## Acceptance (G/W/T) — *this IS the Definition of Done*

**Given** `model_routing.enabled=true` and a recorded COMPLICATED gate
**When** a prompt is submitted
**Then** a hook resolves the role policy and surfaces the routing decision, with the resolved adapter named rather than left empty.

**Given** any `task_mode` — including `system` — under any adapter
**When** `session-context.sh` runs
**Then** a `USER_BANNER` line is always emitted.

**Given** `model_routing.enabled=true`
**When** the banner renders
**Then** it names the resolved adapter/model for the active role.

**Given** a fresh panel with no `.roles`
**When** the banner renders
**Then** the roles field reads `-`, never another panel's chain.

**Given** `cos doctor` runs
**When** its checks execute
**Then** a supervision check reports enabled/mode/threshold and whether dispatch is reachable.

**Given** `cos doctor` runs after the fix
**When** its summary prints
**Then** there are 0 FAIL and every remaining WARN is resolved or documented as expected.

## Work Log
- 2026-08-17 [claude]: Root cause found by executing, not reading: cos_dispatch_formula_run dies under MCP with "asyncio.run() cannot be…
- 2026-08-17 [claude]: Edit agent-supervision.md
- 2026-08-17 [claude]: Edit agent-supervision.md
- 2026-08-17 [claude]: Edit transparency-banner.md
- 2026-08-17 [claude]: Edit transparency-banner.md
- 2026-08-17 [claude]: Plan rationale: consolidate the two divergent nested-loop runners into one _run_async_blocking that probes…
- 2026-08-17 [claude]: Edit _cognition_dispatch.py
- 2026-08-17 [claude]: Edit _cognition_dispatch.py
- 2026-08-17 [claude]: Edit _cognition_dispatch.py
- 2026-08-17 [claude]: Edit _cognition_dispatch.py
- 2026-08-17 [claude]: Edit _cognition_dispatch.py
- 2026-08-17 [claude]: Edit _cognition_dispatch.py
- 2026-08-17 [claude]: Edit _cognition_dispatch.py
- 2026-08-17 [claude]: Edit _dispatch_persistence.py
- 2026-08-17 [claude]: Edit _dispatch_persistence.py
- 2026-08-17 [claude]: Edit _dispatch_persistence.py
- 2026-08-17 [claude]: Edit _dispatch_persistence.py
- 2026-08-17 [claude]: Edit _dispatch_persistence.py
- 2026-08-17 [claude]: Edit _cognition_dispatch.py
- 2026-08-17 [claude]: Edit _cognition_dispatch.py
- 2026-08-17 [claude]: Edit _cognition_dispatch.py
- 2026-08-17 [claude]: Edit _cognition_dispatch.py
- 2026-08-17 [claude]: Edit _cognition_dispatch.py
- 2026-08-17 [claude]: Edit _cognition_dispatch.py
- 2026-08-17 [claude]: Edit _cognition_dispatch.py
- 2026-08-17 [claude]: Edit test_dispatch_safety.py
- 2026-08-17 [claude]: Edit test_dispatch_safety.py
- 2026-08-17 [claude]: Edit test_dispatch_safety.py
- 2026-08-17 [claude]: commit de6fe88a12 — fix(cognition): make formula dispatch survive the MCP event loop
- 2026-08-17 [claude]: Edit resolve_supervise_route.py
- 2026-08-17 [claude]: Edit resolve-supervise-route.sh
- 2026-08-17 [claude]: Edit resolve_supervise_route.py
- 2026-08-17 [claude]: Edit resolve-supervise-route.sh
- 2026-08-17 [claude]: Edit auto-compose-roles.sh
- 2026-08-17 [claude]: Edit registry.yaml
- 2026-08-17 [claude]: Edit adapter.yaml
- 2026-08-17 [claude]: Edit session-context.sh
- 2026-08-17 [claude]: Edit session-context.sh
- 2026-08-17 [claude]: Edit session-context.sh
- 2026-08-17 [claude]: Edit session-context.sh
- 2026-08-17 [claude]: Edit codex-userpromptsubmit-dispatch.sh
- 2026-08-17 [claude]: Edit test_supervision_trigger.py
- 2026-08-17 [claude]: Edit test_supervision_trigger.py
- 2026-08-17 [claude]: Edit test_supervision_trigger.py
- 2026-08-17 [claude]: Edit test_supervision_trigger.py
- 2026-08-17 [claude]: Edit test_supervision_trigger.py
- 2026-08-17 [claude]: Edit test_supervision_trigger.py
- 2026-08-17 [claude]: commit 68c188a29b — feat(hooks): resolve the supervision route per prompt and always show a banner
- 2026-08-17 [claude]: Edit _doctor_supervision.py
- 2026-08-17 [claude]: Edit doctor_checks_runtime.py
- 2026-08-17 [claude]: Edit test_doctor_supervision.py
- 2026-08-17 [claude]: Edit resolve_supervise_route.py
- 2026-08-17 [claude]: Edit resolve_supervise_route.py
- 2026-08-17 [claude]: Edit doctor_checks_runtime.py
- 2026-08-17 [claude]: Edit doctor_checks_runtime.py
- 2026-08-17 [claude]: Edit subsystems.yaml
- 2026-08-17 [claude]: commit cdf1d62d58 — feat(cli): report supervision health in cos doctor
- 2026-08-17 [claude]: Edit live_dispatch_test.py
- 2026-08-17 [claude]: Edit sdk_dispatcher.py
- 2026-08-17 [claude]: Edit sdk_dispatcher.py
- 2026-08-17 [claude]: Edit _dispatch_request.py
- 2026-08-17 [claude]: Edit _dispatch_request.py
- 2026-08-17 [claude]: Edit test_dispatch_safety.py
- 2026-08-17 [claude]: Edit test_dispatch_safety.py
- 2026-08-17 [claude]: Two more dead triggers found the same way: auto-compose-roles.sh produced no chain because formula_composer needs…
- 2026-08-17 [claude]: Live dispatch verified end to end: cos_dispatch_formula_run now returns status=ok with adapter=claude…
- 2026-08-17 [claude]: commit 843b6e8a59 — fix(dispatch): derive the turn budget from the role instead of capping it at one
- 2026-08-17 [claude]: Edit fail-open-hooks-hide-dead-triggers.md
- 2026-08-17 [claude]: Edit MEMORY.md
