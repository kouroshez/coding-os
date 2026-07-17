---
id: TASK-833
title: "Hub routes round-2: bounded reads, field allow-lists, envelope consistency (audit backlog)"
swimlane: core
kind: security
epic: null
labels: [hub, audit, backlog, ready]
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
- **Attacker:** any client that can reach the Hub — the local user always, plus any LAN/remote client when the Hub is bound to a non-loopback host (the COS_HUB_TOKEN gate, TASK-486, is the only guard there).
- **Asset:** Hub worker availability + other projects' session/presence metadata (absolute host paths, raw internal records).
- **Vector:** (a) a request against a large/growing sink (presence JSON, log/trace files) forces an unbounded read()/readlines() -> memory blowup / worker stall (DoS); (b) /presence/now + /sessions return the raw record verbatim -> absolute paths + internal fields leak (info disclosure).
- **Mitigation:** route every file read through the bounded-read helper; return only an allow-listed field set; keep the ok()/fail() envelope so errors don't leak internal detail.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a /api/sessions, /api/observability, /api/logs, or /api/stream read against a large file **When** the handler runs **Then** it reads through the bounded-read helper and never readlines()/read() the whole sink.
- **Given** /api/presence/now or /api/sessions **When** it returns a session/presence record **Then** the payload carries only an explicit allow-list of fields (no absolute host paths, no raw blob).
- **Given** sessions.py responses **When** they are built **Then** they use the ok()/fail() envelope with meta.layer and report the ACTIVE/PRESENT windows imported from board_os.presence (the SSOT), not a local PRESENCE_TTL_S; presence routes carry rate-limit + metrics deps like their siblings.
- **Given** patterns.py **When** an immutable-pattern rejection or a missing table occurs **Then** it maps to the correct category (not 404) and returns a proper envelope (no bare 500).
- **Given** graph.py numeric query params **When** a caller passes a huge max_nodes **Then** it is bounded (le=) below the global ceiling.
- **When** the targeted route tests run **Then** they pass.

## Work Log
