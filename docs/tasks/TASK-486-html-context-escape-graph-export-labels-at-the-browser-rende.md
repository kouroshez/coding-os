---
id: TASK-486
title: "HTML-context-escape graph-export labels at the browser render boundary (never inside _escape)"
swimlane: core
kind: security
epic: null
labels: [hub, xss, ready]
status: archive
priority: P3
appetite: 1d
created: 2026-06-20
started: 2026-06-20
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-486: HTML-context-escape graph-export labels at the browser render boundary (never inside _escape)

**Outcome (one sentence):** When the first browser HTML/mermaid-rendering consumer of graph exports ships, node labels are HTML-context-escaped at the DOM-injection boundary — never inside graph.py _escape(), which must stay mermaid/dot-syntax-only — so attacker- or content-controlled symbol/doc labels cannot become stored XSS. No live sink today (SPA renders only format=json via Sigma WebGL), so this is gated on that first HTML consumer.

## Read First
- src/core/graph_os/tools/graph.py
- src/core/web/ui/src/
- src/core/web/routes/graph.py

## Threat Model
- **Attacker:** a malicious or compromised repository that, when indexed, carries HTML/script markup inside a symbol name, file path, or docstring (e.g. a function or doc-heading whose text is `<img src=x onerror=alert(1)>`), or any extraction path that lets attacker-controlled text reach a node label.
- **Asset:** the operator's browser session on the Hub / an exported HTML graph report — same-origin actions against `/api/*`, the optional `COS_HUB_TOKEN`, and any local-network reach the loopback panel has.
- **Attack vector:** export labels rendered into an HTML/DOM context (a future Hub mermaid/HTML render, or an exported HTML report) WITHOUT HTML-context escaping → stored XSS executing in the viewer's browser when they open the graph.
- **Mitigation:** escape at the HTML render / DOM-injection boundary, NOT in `_escape()` (which is mermaid/dot syntax-only and would corrupt `.mmd`/`.dot`/CLI output if HTML-encoded). Today the only renderer is Sigma's WebGL canvas (`fillText`, not DOM), so the risk is LATENT — this task ships the escaper together with the first HTML/DOM consumer, closing the window before it opens.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** _escape() (graph.py:3478) intentionally produces mermaid/dot syntax-safe text (HTML-entity-encoding it would corrupt CLI/.mmd/.dot output) and the SPA today renders only format=json with no HTML sink, **When** a browser HTML/mermaid render of exported labels is introduced, **Then** HTML-context escaping is applied at that render/DOM-injection point, not in _escape(). **And** a test indexes a node whose label contains '<img src=x onerror=alert(1)>' and asserts it renders inert. **And** _escape() and the CLI/.mmd/.dot output paths remain byte-for-byte unchanged.

## Work Log
- 2026-06-20 [claude]: Edit graph.py
- 2026-06-20 [claude]: Edit test_mcp_tools.py
- 2026-06-20 [claude]: Locked the design half of the task: added a SECURITY comment in _escape (graph.py) documenting it must stay…
- 2026-06-20 [claude]: committed 0ff953b0 · 2 files
- 2026-06-20 [claude]: Edit security.py
- 2026-06-20 [claude]: Edit security.py
- 2026-06-20 [claude]: Edit _envelope.py
- 2026-06-20 [claude]: Edit _envelope.py
- 2026-06-20 [claude]: Edit test_hub_security_gate.py
- 2026-06-20 [claude]: Edit hub-threat-model.md
- 2026-06-20 [claude]: Edit hub-threat-model.md
- 2026-06-20 [claude]: Edit hub-architecture.md
- 2026-06-20 [claude]: commit 40d5f4ca46 — feat(core): gate Hub read routes behind COS_HUB_TOKEN on non-loopback hosts
- 2026-08-02 [claude]: Archive triage 2026-08-02: correctly gated on a consumer that does not exist (SPA renders format=json via Sigma WebGL…
