---
id: TASK-578
title: "Cluster 5 \u2014 Cross-adapter parity: Bash-mediated graph-gate delegate for Codex + dispatcher graph preamble + rename completeness block path"
swimlane: core
kind: feature
epic: graph-first-enforcement
labels: [multi-adapter, codex, parity, dispatcher, graph-gate, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-25
started: 2026-06-25
completed: 2026-06-25
agent_session: ses-system-auto-archive
depends_on: [TASK-573, TASK-577]
blocked_by: []
references: []
---
# TASK-578: Cluster 5 — Cross-adapter parity: Bash-mediated graph-gate delegate for Codex + dispatcher graph preamble + rename completeness block path

**Outcome (one sentence):** hook_renderer.py stops silently dropping a Write/Edit hook for a Bash-only adapter — the `rendered_matcher is None` skip becomes a tracked parity-deficit report (returned/logged) so a dropped enforce gate is visible, not silent (N1); verify-rename-callers gains a real escalation path — when it finds unreplaced callers it records an escalation marker instead of unconditionally exiting 0 (N11). The Codex Bash-mediated graph-gate delegate + dispatcher graph preamble + cos_supervise marker verification (N2) are DEFERRED per the standing "only the Claude adapter matters for now" directive — they are pure Codex-parity value with zero benefit to the Claude-primary path today.

## Read First
- src/cli/hook_renderer.py
- src/core/hooks/verify-rename-callers.sh
- src/adapters/codex/adapter.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*

**Given** the renderer drops a Write/Edit hook for a Bash-only adapter, **When** rendering completes, **Then** a parity-deficit record (adapter + hook id + reason) is produced rather than a silent `continue`.

**Given** verify-rename-callers finds unreplaced callers, **When** it runs, **Then** it records an escalation marker (and warns/blocks per mode) instead of unconditionally exiting 0.

**Then** the adapters + adapter_parity + verify-hooks matrix suites are green.

## Work Log
- 2026-06-25 [claude]: Edit hook_renderer.py
- 2026-06-25 [claude]: Edit hook_renderer.py
- 2026-06-25 [claude]: Edit hook_renderer.py
- 2026-06-25 [claude]: Edit hook_renderer.py
- 2026-06-25 [claude]: Edit hook_renderer.py
- 2026-06-25 [claude]: Edit verify-rename-callers.sh
- 2026-06-25 [claude]: Edit verify-rename-callers.sh
- 2026-06-25 [claude]: Edit verify-rename-callers.sh
- 2026-06-25 [claude]: Edit test_hook_renderer.py
- 2026-06-25 [claude]: Landed: N1 — hook_renderer.py records a _parity_deficits report (adapter+hook+event+matcher+reason) instead of…
