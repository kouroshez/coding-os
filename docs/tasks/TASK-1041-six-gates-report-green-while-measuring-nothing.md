---
id: TASK-1041
title: "Six gates report green while measuring nothing"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-09-18
started: 2026-09-18
completed: 2026-09-18
agent_session: ses-claude-20260918-164827-6f4a
depends_on: []
blocked_by: []
references: []
---
# TASK-1041: Six gates report green while measuring nothing

**Outcome (one sentence):** Every gate either measures what its name claims or says out loud that it does not — no check reports green on a number it never read.

## Read First
- docs/engineering/ci-gates.md (the declared gate SSOT)
- src/core/scripts/docs-staleness-check.sh
- tests/test_file_size_budget.py

## Repro Steps
Six gates, each measured 2026-09-18:

1. **docs-staleness-check.sh is blind.** `make docs-lint` prints
   `MCP tools registered: 1` and `Schema version: 0` on every run. Reality:
   88 distinct `cos_*` tools and migration v54. It greps `server.py` for
   `@mcp.tool` and `database.py` for `MIGRATIONS`; both moved. It has been
   comparing docs against 1 and 0 ever since — and passing.
2. **scaffold-verify enforces nothing.**
   `gh api repos/:owner/:repo/branches/main/protection` → required contexts are
   `["CI Pass"]` only. scaffold-verify ran red on main for 27 days without
   blocking a single merge.
3. **The file-size ratchet watches Python only.** `tests/test_file_size_budget.py:47`
   globs `git ls-files "*.py"`. `OnboardingWizard.tsx` sits at 488 lines — 12 from
   the backstop — completely unwatched at merge time.
4. **`tests/test_codex_chat_provider.py` collects zero tests.** A module-level
   `importorskip("openai_codex")` behind the `codex-sdk` extra that no CI job or
   Makefile target installs. Every job skips it; nothing says so.
5. **`src/core/graph_os/tests/test_brain_overview.py`: 11 tests skipped since
   2026-05-16** on `not hasattr(graph_tools, "cos_graph_overview")` — a symbol
   that exists in no non-test file.
6. **The `sdk_e2e` marker claims a nightly cadence nobody provides.**
   pyproject and conftest both say "nightly only"; no workflow passes
   `--run-sdk-e2e`.

Expected: a gate reports what it measured, or reports that it measured nothing.
Actual: six report green while reading a number that is wrong, absent, or
outside the set they claim to cover.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** `make docs-lint`
**When** it reports the MCP tool count and schema version
**Then** both match what the tree actually holds, and a deliberate drift makes
the gate fail rather than pass.

**Given** a non-Python source file crossing 500 lines
**When** the merge-time ratchet runs
**Then** it is caught, exactly as a `.py` file would be.

**Given** a test file that collects zero tests in CI
**When** the suite runs
**Then** that is surfaced as a failure or the file is removed — a silent
`no tests collected` is not an acceptable resting state.

**Given** scaffold-verify
**When** it fails on main
**Then** either it blocks the merge, or ci-gates.md records it as advisory and
says who reads it.

## Work Log
- 2026-09-18 [claude]: commit a94301e60b — fix(scripts): docs-staleness-check reads live sources and enforces sanity floors
- 2026-09-18 [claude]: Edit patch_gates.py
- 2026-09-18 [claude]: Edit patch_ratchet.py
- 2026-09-18 [claude]: commit 7c0a5d8389 — fix(gates): widen the file-size ratchet past Python and correct ci-gates.md
- 2026-09-18 [claude]: Edit patch_ci.py
- 2026-09-18 [claude]: Edit retire_pr_patterns.py
- 2026-09-18 [claude]: Edit patch_eventclass.py
- 2026-09-18 [claude]: Edit patch_nightly.py
- 2026-09-18 [claude]: Edit patch_nightly_tests.py
- 2026-09-18 [claude]: commit a6ef364865 — fix(diagnostics): stop tests polluting the live log, and grade the right signal
- 2026-09-18 [claude]: Edit dead_ignores.py
- 2026-09-18 [claude]: Edit prune_ignores.py
- 2026-09-18 [claude]: All six blind gates closed. docs-staleness-check read server.py/database.py after both moved, reporting 1 tool /…
- 2026-09-18 [claude]: commit 3dd8804ce6 — chore(doctor): name the remedy, and tighten the complexity ledger
- 2026-09-18 [claude]: Status transitioned to complete via cos task-done.
