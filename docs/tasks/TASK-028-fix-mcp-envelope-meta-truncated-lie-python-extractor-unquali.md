---
id: TASK-028
title: "Fix MCP envelope meta.truncated lie + Python extractor unqualified-import coverage"
swimlane: thinking_os
kind: bug
epic: null
labels: [envelope, extractor, coverage-bug]
status: archive
priority: P1
appetite: "2h"
created: 2026-05-24
started: null
completed: 2026-05-24
agent_session: ses-claude-20260523-174536-44fc
depends_on: []
blocked_by: []
references: []
---
# TASK-028: Fix MCP envelope meta.truncated lie + Python extractor unqualified-import coverage

**Outcome (one sentence):** meta.truncated reflects actual trim; cos_graph_references on symbols imported via unqualified `from <name> import X` returns prod callers (server.py, cli/*) not just tests.

## Read First
- docs/engineering/mcp-error-envelope.md
- docs/engineering/graph-hallucination-cures.md
- docs/engineering/graph_os-queries.md
- src/core/thinking_os/tools/_shared.py
- src/core/graph_os/extractors/code_python.py

## Repro Steps
1. Run `cos_graph_references(uid="code:function:src/core/thinking_os/database.py::init_db", limit=500)`.
2. Observe response: 67 callers, **only test files + one demo script**.
3. Verify ground truth via `grep -rn "init_db" src/core/thinking_os/server.py src/cli/`.
4. Production call-sites (server.py:51, sync_all.py:93, graph_commands.py:77/840, main.py:1071/1212, update.py:346) MISSING from graph.
5. Independent symptom — `cos_graph_impact` envelope returns `meta.truncated=true` while `data.tiers` body is NOT shrunk (response 75KB).

Expected: graph_references returns all static prod callers (≥3 from server.py + sync_all.py + graph_commands.py); envelope `meta.truncated` reflects actual body trim.
Actual: prod callers dropped (module-level call + function-local imports never extracted); envelope flag set unconditionally when serialized size exceeds budget regardless of whether `_apply_token_budget` shrank body.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a `from <bare> import X` at module level AND a module-level call `X()`, AND a function-local `from <pkg> import Y` followed by `Y()` inside that function
- **When** the Python AST extractor processes the file and `link_external_stubs` runs after extraction
- **Then** the resulting graph has a `calls` edge from the caller scope uid to the canonical `code:function:<path>::<name>` uid of the target (no dangling `code:external:unresolved:` for these patterns)
- **And Given** an MCP tool returns `data` shape without a `results` key whose serialized length exceeds TOKEN_BUDGET_CHARS
- **When** `ok(data, meta=...)` envelope-wraps it
- **Then** `data.meta.truncated == False` because no actual trim occurred (envelope honesty preserved)

## Work Log
- 2026-05-24 [claude]: Fix A (envelope): _shared.py _apply_token_budget returns (body, meta, did_trim); caller flips meta.truncated only when d
