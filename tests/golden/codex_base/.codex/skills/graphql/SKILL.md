---
name: graphql
description: Build and operate production GraphQL servers — schema-first SDL design, resolver architecture, the N+1 problem and DataLoader batching, pagination (Relay cursor connections), error handling, schema federation/stitching, persisted queries, and depth/complexity/cost limiting. Use when authoring a GraphQL schema or resolver, debugging N+1 query storms, designing a federated supergraph, hardening a public GraphQL endpoint, or choosing Apollo / graphql-yoga / gqlgen / Strawberry. Boundary vs api-design — api-design owns the protocol-neutral contract decision (REST vs GraphQL, versioning strategy, idempotency keys, RFC 9457 error envelopes for HTTP) and stops at "pick GraphQL"; this skill owns everything GraphQL-internal after that pick (SDL types, resolver/DataLoader runtime, GraphQL-native errors, federation), and defers raw realtime transport to realtime-websockets even when delivering GraphQL subscriptions.
tier: cross-cutting
domain: [backend]
depends_on:
  - api-design
  - clean-code
  - observability
last_reviewed: "2026-06-14"
---

# GraphQL — Schema, Resolvers, Federation, Hardening

A practical guide to running GraphQL in production. Stack-agnostic; concrete patterns reference Apollo Server / graphql-yoga (Node), Strawberry / Ariadne (Python), and gqlgen (Go).

## When to Use This Skill

- Authoring a new GraphQL schema (SDL) or adding types/fields to an existing one.
- Writing or reviewing resolvers — especially when an endpoint is slow under load.
- Diagnosing an N+1 query storm (one list query firing hundreds of row fetches).
- Designing pagination for a GraphQL list field (Relay cursor connections).
- Splitting a monolith schema into a federated supergraph (Apollo Federation / schema stitching).
- Hardening a public GraphQL endpoint against deep/expensive queries.
- Choosing a server library or deciding persisted-queries vs ad-hoc queries.

Skip when: the decision is still "REST or GraphQL" (that is api-design's call), or the transport question is "how do I push live updates over a socket" (that is realtime-websockets).

## Boundary — GraphQL vs api-design vs realtime-websockets

| Concern | Owner |
|---|---|
| REST vs GraphQL decision, versioning posture, idempotency keys, RFC 9457 HTTP error envelope | **api-design** |
| SDL type design, resolver architecture, DataLoader, GraphQL `errors[]` + `extensions`, federation, persisted queries, depth/cost limits | **graphql** (this skill) |
| The websocket transport carrying `graphql-ws` subscription frames, heartbeats, backpressure, reconnect | **realtime-websockets** |

api-design decides *whether* the API is GraphQL and how it errors at the HTTP layer; this skill decides *how* the GraphQL schema and runtime behave once that choice is made. Subscriptions are defined here (the `Subscription` type, resolver, event source) but the socket they ride is realtime-websockets' job.

## Schema-First — SDL Is the Contract

Author the schema in SDL before writing a resolver. The SDL is the source of truth; codegen produces typed resolver signatures from it, never the reverse.

```graphql
type Query {
  order(id: ID!): Order
  orders(first: Int!, after: String): OrderConnection!
}

type Order {
  id: ID!
  status: OrderStatus!
  lineItems: [LineItem!]!   # nullability is a contract — see below
  customer: Customer!
}

enum OrderStatus { PENDING PAID SHIPPED CANCELLED }
```

**Nullability is load-bearing.** A non-null field (`!`) that resolves to null nulls out its *entire parent object* and propagates up to the nearest nullable ancestor. Mark a field non-null only when the resolver can truly never return null; default to nullable for any field backed by a remote call that can fail.

**Design rules:**

- **Nouns and fields, not verbs.** Mutations are the only verbs (`createOrder`, `cancelOrder`). Queries are nouns.
- **One input type per mutation.** `createOrder(input: CreateOrderInput!)` — never a long positional arg list. Additive input fields are non-breaking; positional args are not.
- **Return a payload type from every mutation**, not the bare entity: `type CreateOrderPayload { order: Order, userErrors: [UserError!]! }`. This carries field-level business errors without using the transport `errors[]` array (see error section).
- **Enums over magic strings.** Adding an enum value is non-breaking for outputs; removing one is breaking.

## The N+1 Problem — DataLoader Is Mandatory

The defining GraphQL performance trap: a query for 100 orders, each resolving `customer`, fires 1 + 100 database round-trips. GraphQL resolves fields depth-first per-object, so naive resolvers multiply.

```js
// BAD — one DB hit per order
const resolvers = {
  Order: {
    customer: (order) => db.customer.findById(order.customerId),  // N+1
  },
};

// GOOD — batch within a single tick via DataLoader
const customerLoader = new DataLoader(async (ids) => {
  const rows = await db.customer.findManyByIds(ids);   // ONE query
  const byId = new Map(rows.map((r) => [r.id, r]));
  return ids.map((id) => byId.get(id) ?? null);        // MUST preserve order + arity
});

const resolvers = {
  Order: { customer: (order) => customerLoader.load(order.customerId) },
};
```

**DataLoader rules:**

- **One loader instance per request**, never module-global — a shared loader leaks data across users and never invalidates. Construct loaders in the per-request context factory.
- **The batch function MUST return one result per input key, in input order**, filling misses with `null` (or an `Error` instance). Returning a shorter array silently misaligns every record.
- **Loaders are read caches scoped to one request.** They are not your application cache. For cross-request caching, layer Redis behind the batch function, not in place of the loader.

DataLoader solves batching, not authorization — still authorize each field (see security).

## Pagination — Relay Cursor Connections

GraphQL's de-facto pagination standard is the Relay Connection spec. Use it for any list that can grow.

```graphql
type OrderConnection {
  edges: [OrderEdge!]!
  pageInfo: PageInfo!
  totalCount: Int        # nullable — expensive; omit on huge sets
}
type OrderEdge { node: Order!, cursor: String! }
type PageInfo { hasNextPage: Boolean!, hasPreviousPage: Boolean!, endCursor: String, startCursor: String }
```

- **Cursors are opaque.** Base64 an internal keyset token (e.g. `{sort_value, id}`); never expose a raw offset or DB id as the cursor. Clients must not parse them.
- **`first` + `after` for forward paging; `last` + `before` for backward.** Cap `first`/`last` server-side (e.g. ≤100) and reject larger requests — an uncapped page size is a DoS vector.
- **Prefer keyset over offset** behind the cursor for growing datasets (consistent with api-design's pagination guidance) — offset pagination is race-prone and slow at depth.

## Error Handling — Two Channels, Don't Confuse Them

GraphQL has two distinct error paths:

1. **Transport `errors[]`** (top-level, per the GraphQL spec) — for *exceptional* failures: a resolver threw, a field was unauthorized, the query was malformed. Attach a stable machine code under `extensions.code` (`UNAUTHENTICATED`, `FORBIDDEN`, `NOT_FOUND`, `INTERNAL`). Strip stack traces, SQL, and file paths from `message` in production exactly as api-design's RFC 9457 rule demands for HTTP.

```json
{ "errors": [{ "message": "Order not found",
  "path": ["order"], "extensions": { "code": "NOT_FOUND" } }],
  "data": { "order": null } }
```

2. **`userErrors` in the mutation payload** — for *expected* business outcomes (validation failed, insufficient funds). These are part of `data`, are strongly typed, and never abort the operation. A form that fails validation is a successful query returning `userErrors`, not a transport error.

Rule of thumb: if a frontend would `try/catch` it, it is a transport error; if a frontend would render it next to a field, it is a `userError`.

## Hardening a Public Endpoint

A naked GraphQL endpoint lets a client request an arbitrarily deep, arbitrarily expensive query. Three layers, all required for a public schema:

| Control | Why | Tooling |
|---|---|---|
| **Depth limit** | Stops recursive `friends { friends { friends … } }` blowups | `graphql-depth-limit`, built-in to most servers |
| **Cost/complexity limit** | Caps total resolver work per query (weight fields by expense) | `graphql-query-complexity`, Apollo plugin |
| **Persisted queries (APQ)** | Only pre-registered query hashes run — eliminates arbitrary-query attack surface and shrinks payloads | Apollo APQ, relay persisted |
| **Disable introspection in prod** | Hides the full schema map from attackers (keep it on in staging) | server config flag |
| **Per-field authorization** | DataLoader batches but does not authorize; check the viewer on every protected field | resolver guards / schema directives |

Pair these limits with the rate-limit headers and `429`/`Retry-After` discipline from api-design — GraphQL rides HTTP, so HTTP-layer rate limiting still applies.

## Federation vs Stitching

- **Apollo Federation** (`@key`, `@external`, entity references) — the current standard for composing many subgraph schemas into one supergraph at a gateway. Each team owns a subgraph; the gateway plans cross-subgraph queries. Prefer for multi-team org topologies.
- **Schema stitching** — older, gateway merges remote schemas by type name; more manual conflict resolution. Acceptable for a small number of schemas under one team; federation has largely superseded it.
- **Avoid premature federation.** One team, one schema → a single executable schema. Federate only when subgraph ownership genuinely splits across teams (mirrors anti-overengineering's rule-of-three).

## Observability for GraphQL

Standard HTTP metrics under-report GraphQL because every operation hits one URL (`POST /graphql`). Instrument by **operation name and field**, not by route:

- Tag traces/metrics with the GraphQL `operationName` and the resolved field path, not the URL (otherwise every dashboard shows one endpoint).
- Emit a span per resolver for slow fields; the resolver tree maps cleanly onto an OpenTelemetry span tree (see observability skill).
- Track the `errors[]` rate separately from HTTP 5xx — a GraphQL response is `200 OK` even when `errors[]` is populated, so HTTP-status dashboards miss GraphQL failures entirely.

## Anti-Patterns (reject in review)

1. **Resolver hitting the DB directly without a loader** on a list-reachable field — guaranteed N+1.
2. **Module-global DataLoader** — cross-request data leak + stale cache.
3. **Batch function that returns filtered/reordered results** — misaligns keys to values silently.
4. **Non-null fields backed by fallible remote calls** — one failure nulls the whole parent object.
5. **Business validation thrown as a transport error** — belongs in `userErrors`.
6. **`str(exc)` / stack traces in `errors[].message`** in production — info leak, same as api-design's HTTP rule.
7. **Public endpoint with no depth/cost limit** — trivial DoS.
8. **Versioned schemas (`/graphql/v2`)** — GraphQL evolves by deprecating fields (`@deprecated(reason:)`), not by versioning the endpoint.
9. **`updatedAt: String`** for timestamps — use a scalar that enforces RFC 3339 (`DateTime`).

## Pairs With

- **api-design** — owns the upstream REST-vs-GraphQL decision and the HTTP-layer error/idempotency/rate-limit contract this skill builds on.
- **realtime-websockets** — carries GraphQL subscription frames over a live socket.
- **observability** — operation-level tracing and the `errors[]`-vs-5xx metric split.
- **clean-code** — fail-closed resolvers, no info leak in error messages.

## Source Material

- GraphQL Specification (graphql.org/learn) — the canonical SDL + execution model.
- Relay Cursor Connections Specification — the pagination standard above.
- Apollo Federation docs — subgraph/supergraph composition.
- *Production Ready GraphQL* (Marc-André Giroux) — N+1, security, versioning at scale.
- DataLoader (graphql/dataloader) README — batching + caching contract.
