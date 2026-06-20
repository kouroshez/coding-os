---
id: TASK-460
title: "Dedup record-verify hooks + relocate test harnesses out of src/core/hooks"
swimlane: infra
kind: refactor
epic: audit-remediation-2026-06
labels: [audit-remediation, ready]
status: complete
priority: P3
appetite: 1d
created: 2026-06-20
started: 2026-06-20
completed: 2026-06-20
agent_session: ses-claude-20260619-211916-fd8f
depends_on: []
blocked_by: []
references: []
---
# TASK-460: Dedup record-verify hooks + relocate test harnesses out of src/core/hooks

**Outcome (one sentence):** src/core/hooks/ contains only runtime hooks: record-verify.sh stays (the shared CLI recorder that record-verify-auto.sh delegates to — justified + documented as distinct); test-hooks.sh + verify-agent-system.sh are DELETED, not relocated, because investigation found them dead (no executing caller — make verify-hooks runs shellcheck not them; health_check only checks test-hooks.sh existence) and superseded by the pytest hook suite (tests/test_hooks_*.py) + cos doctor / health_check.py.

## Read First
- src/core/hooks/registry.yaml
- src/core/hooks/record-verify.sh
- src/core/hooks/record-verify-auto.sh
- src/core/thinking_os/health_check.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** src/core/hooks/, **When** listed, **Then** no test-hooks.sh / verify-agent-system.sh remain, and record-verify.sh carries a comment justifying it as the shared recorder distinct from -auto.
**Given** the adapter render + scaffold manifest, **When** regenerated (golden-capture / manifest-regen), **Then** the deleted files drop from fixtures and tests/test_adapters.py + test_adapter_parity.py + test_golden_parity.py pass.
**Given** make verify-hooks and the thinking_os suite (health_check no longer asserts the deleted file), **When** run, **Then** green.

## Work Log
- 2026-06-20 [claude]: Edit record-verify.sh
- 2026-06-20 [claude]: Edit health_check.py
- 2026-06-20 [claude]: Edit health_check.py
- 2026-06-20 [claude]: Edit hook-batching-proposal.md
- 2026-06-20 [claude]: Edit test_adapters.py
- 2026-06-20 [claude]: Edit test_adapters.py
- 2026-06-20 [claude]: Edit test_adapters.py
- 2026-06-20 [claude]: commit 757393263a — test(adapters): align symlink-rules tests with the C1 exclusion
- 2026-06-20 [claude]: commit 73ebbc5b26 — refactor(hooks): retire dead test-hooks.sh + verify-agent-system.sh (TASK-460)
- 2026-06-20 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-20 [claude]: Deleted dead test-hooks.sh + verify-agent-system.sh (no executing caller; superseded by pytest test_hooks_* + cos…
