---
id: TASK-445
title: "Audit 2026-06 no-fork hardening: fix module-gate MCP-name bug (F1) + unify Rule-11 enforcement source (F12) + Hub modules over-promise copy"
swimlane: infra
kind: bug
epic: null
labels: [modularity, audit-2026-06, no-fork, correctness, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-18
started: 2026-06-17
completed: 2026-06-17
agent_session: ses-claude-20260617-183518-6ce2
depends_on: []
blocked_by: []
references: []
---
# TASK-445: Audit 2026-06 no-fork hardening: fix module-gate MCP-name bug (F1) + unify Rule-11 enforcement source (F12) + Hub modules over-promise copy

**Outcome (one sentence):** Three verified correctness/honesty fixes independent of the open architecture forks — the module capability-gate keys on the registered MCP name (so disabling memory actually gates cos_search/cos_timeline/cos_details), the Rule-11 checker docstring no longer falsely claims it mirrors the test, and the Hub Modules copy stops over-promising AGENTS.md section stripping.

## Read First
- src/core/thinking_os/tools/_shared.py
- src/core/thinking_os/server.py
- src/core/scripts/check_hardcoded_literals.py
- src/core/web/ui/src/pages/ConfigPage.tsx
- docs/engineering/mcp-error-envelope.md

## Repro Steps
`cos module disable memory`, then call cos_search → it RAN instead of returning module_disabled, because _shared.py:862 called _gated_module(fn.__name__='thinking_os_search') which matched neither the 'cos_search' entry nor any prefix (server registers name='cos_search'). Separately: check_hardcoded_literals.py docstring claimed it "Mirrors the logic in tests/test_no_hardcoded_stacks.py so the hook and the test agree" — false; the test uses a frozen 6-item set while the checker uses discover_literals() over all yaml + skills.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the memory module disabled **When** cos_search / cos_timeline / cos_details are invoked **Then** they return a `module_disabled` envelope (safe_tool gained an optional name= so the gate keys on the registered MCP name), and test_module_gate_registry exercises the live FastMCP registry to guard against future drift. [DONE — commit c06e7163]

**Given** the false 'mirrors' docstring in check_hardcoded_literals.py **When** a maintainer reads it **Then** it states the truth: the checker is data-driven over all yaml and does NOT yet share its set with the test, with the unification (narrow to stack/adapter ids, drop skills, handle ambiguous go/meta/python) tracked in TASK-441. [DONE — commit 3034a454]. NOTE: the full test↔checker unification is DEFERRED to TASK-441 — a blast-radius probe found discover_literals() raw would raise 30 false positives on cli/*.py (skill names + ambiguous short ids colliding with path components/dict keys), so it is a forked design change, not a no-fork edit.

**Given** the Hub Modules tab **When** it renders the disable copy **Then** the text states only what disabling does today (MCP tools gated + hooks self-skip), not 'AGENTS.md sections' which only 1 of 6 modules currently drops. [DONE — commit 3034a454]

**Given** all three fixes **When** the matrix suites run **Then** they pass: thinking_os 1417 passed + server --test exit 0 (verified); checker syntax + logic intact (verified).

## Work Log
- 2026-06-18 [claude]: DONE. F1 (c06e7163): safe_tool gained name=; 3 server registrations pass it; test_module_gate_registry added;…
