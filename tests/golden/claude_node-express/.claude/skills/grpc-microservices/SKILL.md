---
name: grpc-microservices
description: Build and operate gRPC services and the service-to-service mesh — Protobuf schema design with wire-compatible evolution, the four RPC kinds (unary, server/client/bidi streaming), deadline propagation, retries and hedging, status-code semantics, interceptors for auth/tracing/metrics, mTLS, load balancing (client-side vs proxy/mesh), and gRPC-Gateway for a REST edge. Use when defining a .proto contract, choosing gRPC vs REST for internal traffic, debugging DEADLINE_EXCEEDED or backward-incompatible schema changes, wiring interceptors, or designing a microservice mesh. Boundary vs api-design — api-design owns the public/external HTTP contract (REST/GraphQL, RFC 9457 envelopes, idempotency keys) for heterogeneous consumers; this skill owns binary east-west gRPC between services controlled on both sides, including Protobuf evolution and gRPC status codes. Defers raw long-lived bidirectional sockets to realtime-websockets and the REST translation edge to api-design.
tier: cross-cutting
domain: [backend]
depends_on:
  - api-design
  - clean-code
  - observability
last_reviewed: "2026-06-14"
---

# gRPC + Microservices — Protobuf, RPC, Mesh

A practical guide to gRPC for east-west (service-to-service) traffic. Stack-agnostic; concrete patterns reference `grpc-go`, `grpcio` (Python), and `@grpc/grpc-js` (Node), with Envoy / a service mesh as the proxy layer.

## When to Use This Skill

- Defining or evolving a `.proto` service contract.
- Choosing gRPC vs REST/GraphQL for traffic *between services you control on both ends*.
- Debugging `DEADLINE_EXCEEDED`, `UNAVAILABLE`, or a backward-incompatible Protobuf change.
- Designing streaming RPCs (server-stream, client-stream, bidi).
- Wiring interceptors for auth, tracing, metrics, retries.
- Standing up mTLS, client-side load balancing, or a gRPC mesh.
- Exposing a gRPC service to external REST clients via gRPC-Gateway.

Skip when: the consumer is a browser/mobile/3rd-party over public HTTP (that is api-design's REST/GraphQL territory), or the need is a long-lived bidirectional *browser* socket (that is realtime-websockets).

## Boundary — gRPC vs api-design vs realtime-websockets

| Concern | Owner |
|---|---|
| Public, external, heterogeneous HTTP API (REST/GraphQL), RFC 9457 envelopes, URL/header versioning, idempotency keys | **api-design** |
| Binary east-west gRPC between controlled services: Protobuf evolution, the four RPC kinds, gRPC status codes, deadlines, interceptors, mesh | **grpc-microservices** (this skill) |
| Long-lived bidirectional sockets to browsers (WebSocket/SSE), heartbeats, reconnect, fan-out | **realtime-websockets** |

The split is **who controls both ends and over what network**. api-design serves consumers that cannot be coordinated and speak HTTP/JSON; this skill serves internal services that share a generated stub and speak HTTP/2 + Protobuf. When a gRPC service must face external REST clients, gRPC-Gateway translates at the edge — and that REST surface is then governed by api-design.

## Protobuf — Schema Evolution Is the Whole Game

The `.proto` is the contract; the wire format is field-number-based, which makes additive evolution safe and renames cheap — *if* the rules are followed.

```protobuf
syntax = "proto3";
package orders.v1;

message Order {
  string id = 1;
  OrderStatus status = 2;
  int64 created_at_unix = 3;
  reserved 4;                 // a removed field's number — NEVER reuse
  reserved "legacy_total";    // and its name
  string customer_id = 5;
}

enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;  // proto3 enums MUST have a zero default
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_PAID = 2;
}

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (Order);
}
```

**Wire-compatibility rules (violating these breaks deployed clients):**

- **Field numbers are forever.** Adding a field = new number = backward-compatible. Removing a field → `reserved` its number and name so they are never reused.
- **Never change a field's type or number.** `int32`→`int64` is wire-compatible in some cases but `int`→`string` is not; treat type changes as breaking.
- **Every proto3 enum needs a `_UNSPECIFIED = 0`** default — an unset enum reads as zero, and a meaningful zero hides "field absent".
- **Package the version (`orders.v1`).** A genuinely breaking redesign ships as `orders.v2` in a new package, run side-by-side — the gRPC analog of api-design's URL versioning.
- **Buf for lint + breaking-change detection in CI** — `buf breaking` against the main branch is the gRPC equivalent of api-design's schema/contract tests; make it a merge gate.

## The Four RPC Kinds

| Kind | Shape | Use when |
|---|---|---|
| **Unary** | 1 req → 1 resp | The default; most calls. Maps to a REST-like operation. |
| **Server streaming** | 1 req → N resp | Server pushes a sequence: a result feed, progress, a large paged export. |
| **Client streaming** | N req → 1 resp | Client uploads a stream: telemetry ingest, chunked upload, aggregation. |
| **Bidirectional** | N req ↔ N resp | Both stream independently: chat-like internal protocols, live sync. |

Streaming RPCs are *internal* plumbing. For browser-facing live updates, prefer WebSocket/SSE (realtime-websockets) — browsers cannot speak native gRPC streaming without grpc-web's limitations.

## Deadlines — Propagate, Never Drop

The single most important gRPC reliability discipline: **every call carries a deadline, and the deadline propagates down the call chain.** Without it, a slow downstream service holds the whole chain's threads hostage and cascades into a fleet-wide outage.

```go
// Caller sets an absolute deadline; gRPC propagates it as a header.
ctx, cancel := context.WithTimeout(ctx, 300*time.Millisecond)
defer cancel()
resp, err := client.GetOrder(ctx, &pb.GetOrderRequest{Id: id})

// Callee budgets the REMAINING time across its own downstream calls.
if deadline, ok := ctx.Deadline(); ok && time.Until(deadline) < dbBudget {
    return nil, status.Error(codes.DeadlineExceeded, "insufficient time budget")
}
```

- **Set a deadline on every outbound call** — a missing deadline is an unbounded hang.
- **Budget the remaining deadline across downstream calls** — do not pass the full parent deadline to each child; the chain must fit inside the caller's budget.
- **Cancellation propagates** — when the caller's context is cancelled, abort in-flight downstream work; do not finish wasted computation.

## Status Codes + Retries

gRPC has its own status enum (not HTTP statuses). Map domain errors to the right code — clients (and retry policies) branch on it.

| gRPC code | Meaning | Retryable? |
|---|---|---|
| `OK` | success | — |
| `INVALID_ARGUMENT` | client sent bad input | no |
| `NOT_FOUND` | entity absent | no |
| `ALREADY_EXISTS` / `FAILED_PRECONDITION` | conflict / state mismatch | no |
| `PERMISSION_DENIED` / `UNAUTHENTICATED` | authz / authn | no |
| `DEADLINE_EXCEEDED` | ran out of time | yes (with backoff) |
| `UNAVAILABLE` | transient — server down/restarting | yes (with backoff) |
| `RESOURCE_EXHAUSTED` | rate-limited / quota | yes (honor backoff) |
| `INTERNAL` / `UNKNOWN` | server bug | no (don't retry a bug) |

- **Retry only the retryable codes**, with exponential backoff + jitter, via the built-in gRPC retry policy (service config) — not hand-rolled loops.
- **Retries require idempotency.** A retried mutation must be safe — pass an idempotency key in metadata (consistent with api-design's idempotency rule) so a duplicate is deduped server-side.
- **Hedging** (fire a second attempt after a delay, take the first response) cuts tail latency for read-heavy paths — enable it only for genuinely idempotent reads.
- **Strip internals from status messages** in production — no stack traces or SQL in the `status.message`, same discipline as api-design's HTTP errors. Use `error_details` (`google.rpc.Status`) for structured, machine-readable detail.

## Interceptors — Cross-Cutting Plumbing

Interceptors (middleware) are where auth, tracing, metrics, and retries live — never copy-pasted into each handler.

- **Order matters:** recovery (panic → `INTERNAL`) outermost, then tracing, then auth, then metrics, then the handler. A panic must never crash the server process.
- **Auth interceptor** validates the token from call metadata and injects the identity into context; handlers read identity from context, never re-parse the token.
- **Tracing/metrics interceptors** emit one span + RED metrics per RPC automatically (see observability) — tag by `service/method`, never by a per-entity id (cardinality).

## Transport Security + Load Balancing

- **mTLS for east-west by default.** Services authenticate *each other* with certificates; a service mesh (Istio/Linkerd) can provide this transparently, or do it in-process. Plaintext gRPC belongs only inside a trusted boundary, never across one.
- **Load balancing is L7, not L4.** gRPC multiplexes many calls over one long-lived HTTP/2 connection, so a naive L4 (TCP) load balancer pins all traffic to one backend. Use **client-side LB** (gRPC's `round_robin`/`pick_first` + service discovery) or an **L7 proxy/mesh** (Envoy) that understands HTTP/2 streams.
- **Connection reuse:** keep a long-lived channel per upstream; do not open a channel per call (the handshake cost dominates). Tune keepalive pings so idle channels stay healthy through proxies.

## gRPC-Gateway — The REST Edge

When external clients need REST/JSON over a gRPC service, generate a reverse-proxy from `google.api.http` annotations.

- Annotate RPCs (`option (google.api.http) = { get: "/v1/orders/{id}" }`); gRPC-Gateway emits a REST handler that transcodes JSON↔Protobuf.
- **The REST surface it exposes is governed by api-design** — RFC 9457 errors, pagination, versioning all apply to that edge. gRPC owns the internal contract; api-design owns the translated public one. Keep the two boundaries explicit so the same operation does not get two competing error formats.

## Anti-Patterns (reject in review)

1. **Reusing a `reserved` field number** — silently corrupts deployed clients reading the old number.
2. **Changing a field's type or number** in place — wire-incompatible; ship a v2 package instead.
3. **No `_UNSPECIFIED = 0` enum default** — unset reads as a real value, hiding "absent".
4. **Calls without a deadline** — an unbounded hang that cascades across the mesh.
5. **Passing the full parent deadline to every child** — the chain can't fit; budget it.
6. **Retrying non-idempotent mutations** or non-retryable codes (`INVALID_ARGUMENT`, `INTERNAL`).
7. **L4 load balancer in front of gRPC** — pins all multiplexed calls to one backend.
8. **A channel per call** — pays the HTTP/2 + TLS handshake every time.
9. **Plaintext gRPC across a trust boundary** — east-west traffic needs mTLS.
10. **Stack traces / SQL in `status.message`** — info leak, same as api-design's HTTP rule.

## Pairs With

- **api-design** — owns the external REST/GraphQL contract and the gRPC-Gateway REST edge; this skill owns the internal binary contract.
- **realtime-websockets** — for browser-facing live streams (gRPC streaming is internal-only).
- **observability** — per-RPC spans and RED metrics via interceptors.
- **clean-code** — interceptor ordering, fail-closed handlers, no info leak in status messages.

## Source Material

- Protocol Buffers Language Guide (proto3) + the official schema-evolution rules.
- gRPC Core Concepts (grpc.io) — RPC kinds, deadlines, status codes, channels.
- `buf` documentation — lint + breaking-change detection in CI.
- gRPC-Gateway docs — `google.api.http` transcoding to REST.
- *gRPC: Up and Running* (Indrasiri & Kuruppu) — interceptors, security, deployment.
