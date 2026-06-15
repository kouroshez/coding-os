---
name: realtime-websockets
description: Build production realtime servers over WebSockets and Server-Sent Events — connection lifecycle, the heartbeat/ping-pong + idle-timeout contract, automatic reconnection with exponential backoff and resume tokens, backpressure and per-connection send queues, horizontal scale-out via a Redis/NATS pub-sub fan-out, presence tracking, and auth on the upgrade handshake. Use when adding live updates (chat, notifications, collaborative cursors, live dashboards), choosing WebSocket vs SSE vs long-poll, debugging dropped or zombie connections, or scaling a socket server past one node. Boundary vs api-design — api-design owns request/response HTTP contracts (REST/GraphQL, idempotency, RFC 9457 errors) and stops at the protocol-upgrade boundary; this skill owns the persistent bidirectional connection after upgrade. Carries higher-level subscription protocols (e.g. graphql-ws) as transport but defers their payload schema to graphql.
tier: cross-cutting
domain: [backend]
depends_on:
  - api-design
  - clean-code
  - observability
last_reviewed: "2026-06-14"
---

# Realtime — WebSockets + Server-Sent Events

A practical guide to running persistent realtime connections in production. Stack-agnostic; concrete patterns reference `ws`/Socket.IO (Node), `websockets`/Starlette (Python), `gorilla/websocket` + `melody` (Go), and Redis/NATS as the fan-out bus.

## When to Use This Skill

- Adding live updates: chat, notifications, presence, collaborative editing, live dashboards, order/status streams.
- Choosing between WebSocket, Server-Sent Events (SSE), and long-polling.
- Debugging dropped connections, zombie sockets, or "the client thinks it's connected but messages stop arriving".
- Implementing reliable reconnection (backoff, resume, missed-message replay).
- Scaling a socket server beyond one process/node (fan-out across instances).
- Authenticating and authorizing a connection at the upgrade handshake.

Skip when: the interaction is request/response (use HTTP — that is api-design), or the question is the *schema* of subscription payloads (that is graphql for `graphql-ws`).

## Boundary — Realtime vs api-design vs graphql

| Concern | Owner |
|---|---|
| REST/GraphQL request-response contracts, versioning, idempotency keys, RFC 9457 HTTP errors | **api-design** |
| The persistent connection after upgrade: lifecycle, heartbeat, reconnect, backpressure, fan-out, presence | **realtime-websockets** (this skill) |
| The schema/shape of messages flowing over a `graphql-ws` subscription | **graphql** |

api-design governs everything up to (and including) the HTTP request that *opens* the socket — the `Upgrade` handshake is an HTTP request and its auth/error semantics follow api-design. Once the connection is established and bidirectional, this skill takes over. Message *payload schemas* belong to whoever owns the domain (graphql for GraphQL subscriptions, or a plain JSON envelope this skill defines).

## Transport Decision — WebSocket vs SSE vs Long-Poll

| Transport | Direction | Reconnect | Use when | Avoid when |
|---|---|---|---|---|
| **SSE** (`text/event-stream`) | server → client only | built-in (`Last-Event-ID`, auto-retry) | server-push only: notifications, live feeds, log tails, LLM token streams | the client must also push frequently |
| **WebSocket** | full duplex | manual (build it) | chat, collaboration, gaming, anything bidirectional and chatty | a one-way feed where SSE's simplicity wins |
| **Long-poll** | request/response | n/a | last-resort fallback where WS/SSE are blocked by middleboxes | anything modern can do — it is a fallback, not a default |

**Default: SSE for one-way push, WebSocket for true bidirectional.** SSE rides plain HTTP/2, reconnects itself, and passes proxies cleanly — reach for WebSocket only when the client genuinely needs to push. (LLM token streaming → SSE; see llm-patterns.)

## Connection Lifecycle — The State Machine

Every connection moves through `CONNECTING → OPEN → CLOSING → CLOSED`. Production code must handle all four plus the half-open failure mode where the TCP connection is dead but neither side has noticed.

- **On open:** authenticate (see handshake auth), register the connection in the per-node registry, send any buffered/missed messages if a resume token was presented.
- **On message:** validate the frame shape before dispatch; never `eval`/trust client input.
- **On close:** deregister from the registry AND the pub-sub bus, flush presence, cancel timers. A leaked registry entry is a memory leak that compounds per reconnect.
- **On error:** treat as close — clean up identically. Do not assume `error` fires before `close`.

## Heartbeat — The Zombie-Connection Cure

TCP can silently die (laptop sleeps, NAT drops the mapping) leaving a socket that is `OPEN` on both sides but transports nothing. The cure is an application-level heartbeat, not reliance on TCP keepalive (whose default ~2h timeout is useless).

```js
// Server: ping every 30s; terminate a socket that missed the prior pong.
const HEARTBEAT_MS = 30_000;
function heartbeat(ws) { ws.isAlive = true; }
const timer = setInterval(() => {
  for (const ws of wss.clients) {
    if (ws.isAlive === false) { ws.terminate(); continue; } // missed last pong → zombie
    ws.isAlive = false;
    ws.ping();
  }
}, HEARTBEAT_MS);
wss.on("connection", (ws) => { ws.isAlive = true; ws.on("pong", () => heartbeat(ws)); });
```

**Rules:** ping interval < proxy idle timeout (most LBs/NGINX default 60s — ping at ~30s). A missed pong on the *next* cycle means terminate, not "wait one more". SSE uses a periodic comment line (`: keepalive\n\n`) for the same purpose.

## Reconnection — Client Backoff + Server Resume

Networks drop. The client must reconnect; the server must let it resume without losing or duplicating messages.

- **Exponential backoff with jitter** on the client: `min(cap, base * 2^attempt) ± rand`. Never reconnect in a tight loop — a server restart with 10k clients all retrying at 1s is a self-inflicted DoS (thundering herd).
- **Resume token / sequence number:** the server tags each message with a monotonic seq; the client sends its last-seen seq on reconnect; the server replays the gap from a short-lived per-connection buffer (or a Redis stream). SSE gives this for free via `Last-Event-ID`.
- **Idempotent message handling on the client** — at-least-once replay means a message can arrive twice; dedupe by seq/id.

## Backpressure — A Slow Client Must Not OOM the Server

A fast producer + a slow consumer fills the kernel send buffer; unbounded server-side queuing then exhausts memory. This is the realtime equivalent of an unbounded list endpoint.

- **Check the socket's buffered-amount before each send.** Past a threshold (e.g. `ws.bufferedAmount > 1MB`), drop the slowest-tolerable messages (coalesce presence/cursor updates) or disconnect the client with a `1013 Try Again Later`.
- **Bounded per-connection queue**, newest-wins for ephemeral state (cursor position), oldest-preserved for events that must not be lost (chat). Pick the policy per message class; never an unbounded queue.
- **Coalesce high-frequency updates** (typing indicators, cursor moves) to a max rate (e.g. 20/s) server-side before they hit the wire.

## Scaling Out — Fan-Out Across Nodes

A WebSocket is stateful: the connection lives on exactly one node. With N nodes behind a load balancer, a message published on node A must reach a subscriber connected to node B. A pub-sub bus is the standard fix.

```
client ──┐                       ┌── node A ──┐
         ├─ load balancer ───────┤            ├─ Redis Pub/Sub ─┐
client ──┘   (sticky sessions)   └── node B ──┘   (or NATS)     │
                                       ▲                         │
                                       └──── fan-out ────────────┘
```

- **Each node subscribes to the bus**; a publish on any node fans out to every node, which forwards to its locally-connected subscribers. Redis Pub/Sub, NATS, or a Kafka topic are all valid — Redis is the common default.
- **Sticky sessions (or a connection registry)** so reconnects and request-affinity land predictably; the bus removes the *hard* requirement for stickiness but it still simplifies presence.
- **Presence at scale** lives in a shared store (Redis set/hash with TTL refreshed by the heartbeat), not in per-node memory — otherwise "who is online" is wrong the moment there is more than one node.

## Auth on the Handshake

The `Upgrade` request is a normal HTTP request — authenticate it there, following api-design's auth rules, before the socket opens.

- **Authenticate at upgrade, not after.** Reject with a `401` during the handshake; never accept the socket and then check. A common pattern: short-lived ticket — client gets a one-time token from an authed REST endpoint, presents it on the WS connect, server validates and burns it.
- **Browsers cannot set custom headers on a WebSocket** — pass the token via the ticket pattern, a `Sec-WebSocket-Protocol` subprotocol value, or a cookie (with CSRF protection); avoid putting long-lived secrets in the URL query string (they leak into access logs).
- **Re-authorize per message for sensitive actions** — connection-time auth proves identity once; a long-lived socket still needs per-action authorization, exactly as a long-lived session does.
- **Origin check** the handshake to blunt cross-site WebSocket hijacking; WS does not honor the same-origin policy by default.

## Observability for Realtime

Connection-oriented metrics differ from request metrics — instrument the *fleet of connections*:

- **Gauges:** concurrent connections, connections per node, presence-set size.
- **Counters:** connects, disconnects (tagged by close code), messages in/out, dropped-for-backpressure.
- **Histograms:** connection lifetime, message fan-out latency (publish → delivered).
- **Alert** on a disconnect spike (mass reconnect storm), a climbing per-connection buffer (backpressure), and pub-sub lag. Per-user data goes on logs/traces, never as a metric label (cardinality — see observability).

## Anti-Patterns (reject in review)

1. **No application heartbeat** — zombie half-open connections accumulate; the server thinks thousands are live.
2. **Relying on TCP keepalive** for liveness — its multi-hour default never fires in time.
3. **Reconnect with no backoff/jitter** — thundering-herd DoS on every server restart.
4. **Unbounded per-connection send queue** — one slow client OOMs the node.
5. **Per-node in-memory presence with >1 node** — "online users" is wrong the instant the fleet scales.
6. **Auth checked after the socket opens** instead of on the upgrade handshake.
7. **Secret token in the WS URL query string** — leaks into access logs and proxies.
8. **WebSocket for a one-way feed** where SSE would auto-reconnect and pass proxies for free.
9. **Forgetting to deregister on close** — registry/pub-sub leak that grows per reconnect.

## Pairs With

- **api-design** — owns the HTTP handshake's auth/error contract and the request/response side of the API.
- **graphql** — defines the payload schema for `graphql-ws` subscriptions this transport carries.
- **observability** — connection-fleet gauges, disconnect/backpressure alerts.
- **llm-patterns** — SSE is the canonical transport for streaming LLM tokens.

## Source Material

- RFC 6455 — The WebSocket Protocol (handshake, close codes, framing).
- WHATWG HTML — Server-Sent Events (`EventSource`, `Last-Event-ID`, auto-retry).
- `graphql-ws` protocol — the modern GraphQL-over-WebSocket subprotocol.
- Redis Pub/Sub + Redis Streams docs — fan-out and replay buffers.
- "Scaling WebSockets" (Ably / PubNub engineering write-ups) — fleet-level patterns.
