---
id: TASK-956
title: "Unblock the release: stale api-types, database.py over budget, install.sh shellcheck"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: complete
priority: P0
appetite: 1d
created: 2026-08-12
started: 2026-08-12
completed: 2026-08-12
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-956: Unblock the release: stale api-types, database.py over budget, install.sh shellcheck

**Outcome (one sentence):** The release-please CI run is green so the pending version can publish: generated api-types match the served routes, database.py is back under the 500-line gate, and install.sh passes shellcheck.

## Read First
- tests/test_api_types_drift.py
- tests/test_file_size_budget.py
- tests/test_install_script.py
- src/core/thinking_os/database.py

## Repro Steps
On main and on the release-please PR branch (a77cda3e), `uv run pytest tests/test_api_types_drift.py tests/test_file_size_budget.py tests/test_install_script.py -q` reports 4 failures: api-types.ts lacks /api/config/mcp/{server_id} and still lists the removed /api/config/mcp/{name}; src/core/thinking_os/database.py is 502 lines against the 500 gate; install.sh has shellcheck findings. CI run 31620109286 fails on the same four.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the four failing cross-cutting guards on main
**When** the generated types are regenerated, database.py is split at a cohesive seam rather than baselined, and the shellcheck findings in install.sh are fixed
**Then** all four suites pass locally and the release-please CI run reports success.

## Work Log
- 2026-08-12 [claude]: Edit install.sh
- 2026-08-12 [claude]: Edit _db_pool.py
- 2026-08-12 [claude]: commit 68f2d2b9ae — fix(release): unblock CI — regenerate api-types, split db pool, clean shellcheck
- 2026-08-12 [claude]: Edit MemoryCards.tsx
- 2026-08-12 [claude]: Edit memory-derive.ts
- 2026-08-12 [claude]: Edit memory-derive.ts
- 2026-08-12 [claude]: Edit memory-derive.test.ts
- 2026-08-12 [claude]: commit 65cb7943ed — feat(hub): rebuild the Memory tab around the trust ladder
- 2026-08-12 [claude]: Status transitioned to complete via cos task-done.
