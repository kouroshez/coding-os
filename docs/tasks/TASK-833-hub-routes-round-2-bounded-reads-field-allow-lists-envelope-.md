---
id: TASK-833
title: "Hub routes round-2: bounded reads, field allow-lists, envelope consistency (audit backlog)"
swimlane: core
kind: security
epic: null
labels: [hub, audit, backlog]
status: icebox
priority: P2
appetite: 1d
created: 2026-07-17
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-833: Hub routes round-2: bounded reads, field allow-lists, envelope consistency (audit backlog)

**Outcome (one sentence):** Close the remaining audit route findings: sessions.py (unbounded presence read + raw-record/absolute-path info disclosure + envelope bypass + stale TTL vs board_os.presence SSOT + no rate-limit), stream.py + search.py + cognition.stream_trace unbounded reads, presence.py raw-blob allow-list, patterns.py 404-mapping + missing-table 500, graph.py unbounded max_nodes (add le=). Each: bounded-read helper, field allow-list, ok()/fail() envelope, import windows from board_os.presence.

## Read First
- src/core/web/routes/sessions.py
- src/core/board_os/presence.py
- src/core/web/routes/_bounded_read.py

## Threat Model
(fill in: attacker, asset, attack vector, mitigation)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
