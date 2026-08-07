---
id: TASK-896
title: "docs-update: sync model-routing rule to enforced supervision trigger modes"
swimlane: docs
kind: chore
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-08-07
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-896: docs-update: sync model-routing rule to enforced supervision trigger modes

## Outcome

`src/core/rules/model-routing.md` — injected into every session — describes the supervision trigger modes as they are now enforced (explicit = policy always applies; adaptive = complexity-gated; suggest = dry run returning `proposed_route`), instead of the pre-implementation wording that promised an approval prompt which does not exist.

## Read First

- `docs/engineering/agent-supervision.md` — the contract SSOT this rule summarizes.
- `src/core/thinking_os/supervision.py::policy_applies` — the enforced predicate.

## Acceptance

- **Given** an agent session with supervision enabled
- **When** the model-routing rule is injected
- **Then** its mode descriptions match `policy_applies` behaviour, and the golden adapter fixtures are regenerated.

## Work Log
- 2026-08-07 [claude]: Edit model-routing.md
- 2026-08-07 [claude]: Edit SettingsPage.tsx
- 2026-08-07 [claude]: Edit SettingsPage.test.tsx
- 2026-08-07 [claude]: Edit SettingsPage.test.tsx
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit README.md
- 2026-08-07 [claude]: Edit agent-supervision.md
- 2026-08-07 [claude]: Edit agent-supervision.md
- 2026-08-07 [claude]: Edit test_hub_settings_model_routing.py
- 2026-08-07 [claude]: Edit test_hub_settings_model_routing.py
- 2026-08-07 [claude]: Edit test_hub_settings_model_routing.py
- 2026-08-07 [claude]: commit 80328bca22 — fix(supervision): enforce trigger modes and make the orchestrator target the role default
- 2026-08-07 [claude]: commit a6e360f407 — fix(hub): keep a saved supervision target visible when its adapter is unavailable
- 2026-08-07 [claude]: commit 61f6f66970 — test(supervision): cover trigger-mode gating, write-time validation, and stale targets
- 2026-08-07 [claude]: commit 504d29cd9a — docs(supervision): document the enforced contract, add the operator playbook and README section
- 2026-08-07 [claude]: commit cdb8963032 — docs(rules): sync the model-routing rule to the enforced supervision trigger modes
