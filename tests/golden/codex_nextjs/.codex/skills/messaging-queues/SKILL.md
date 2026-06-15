---
name: messaging-queues
description: Design production async messaging — queues, brokers, pub/sub, event streams, and the delivery-guarantee math behind them. Use when introducing a message broker (RabbitMQ / Kafka / SQS / NATS / Redis Streams), choosing queue vs log vs pub/sub, designing idempotent consumers, sizing retries and dead-letter queues, ordering partitions, handling poison messages, or debugging duplicate/lost/out-of-order delivery. Boundary vs api-design — api-design owns the synchronous request/response HTTP contract (REST/GraphQL, idempotency keys, RFC 9457 errors) where the caller waits for a reply; this skill owns the asynchronous fire-and-forget seam after a request returns, where producer and consumer are decoupled in time. Defers the persistent bidirectional socket transport to realtime-websockets and binary east-west RPC to grpc-microservices.
tier: cross-cutting
domain: [backend]
depends_on:
  - clean-code
  - observability
last_reviewed: "2026-06-14"
---

# Messaging & Queues — Async Delivery That Survives Failure

A practical guide to moving work off the request path and across service boundaries without losing, duplicating, or reordering it into corruption. Stack-agnostic; concrete recipes target RabbitMQ, Kafka, AWS SQS/SNS, NATS, and Redis Streams as the reference brokers.

## When to Use This Skill

- Introducing the first broker into a system that has only synchronous HTTP calls.
- Choosing between a work queue, an event log, and pub/sub fan-out for a new flow.
- Designing a consumer that must be safe to retry — idempotency, dedup, exactly-once illusions.
- Sizing retry/backoff, dead-letter queues, and poison-message handling before launch.
- Debugging duplicate processing, lost messages, or out-of-order delivery in production.
- Deciding partition keys / ordering guarantees for an event stream.

Skip when: the caller needs the result synchronously in the same request — that is an HTTP/RPC contract (see api-design / grpc-microservices), not a queue.

## The First Decision — Queue vs Log vs Pub/Sub

These three are not interchangeable. Pick by who consumes and whether history matters.

| Shape | Semantics | Each message goes to | Use when | Reference broker |
|---|---|---|---|---|
| **Work queue** | competing consumers, message removed on ack | exactly one worker in the pool | distribute jobs, scale horizontally | RabbitMQ, SQS |
| **Event log** | append-only, retained, replayable by offset | every consumer group, independently | event sourcing, audit, replay, multiple readers | Kafka, Redis Streams |
| **Pub/Sub** | fan-out, fire-and-forget, no retention | every live subscriber once | broadcast notifications, cache invalidation | SNS, NATS, Redis pub/sub |

The classic mistake is reaching for Kafka when a work queue is wanted (now there is partition/offset/consumer-group machinery for a job dispatcher) or using a pub/sub broadcast when at-least-once durable delivery is required (subscribers offline at publish time silently miss the message).

## Delivery Guarantees — Know Which One the Broker Actually Gives

| Guarantee | What it means | Cost | Reality |
|---|---|---|---|
| **At-most-once** | fire, never retry; may lose | cheapest | acceptable only for disposable signals (metrics ticks) |
| **At-least-once** | retry until acked; may duplicate | moderate | the practical default for almost everything |
| **Exactly-once** | delivered and processed once | expensive, often a lie | only within a broker's transactional boundary (Kafka EOS), never end-to-end across an arbitrary side effect |

**The load-bearing rule: design for at-least-once and make the consumer idempotent.** "Exactly-once delivery" across a network and a non-transactional side effect (charge a card, send an email) does not exist. What exists is at-least-once delivery + an idempotent consumer = effectively-once *processing*. Build that.

## Idempotent Consumers — The Core Pattern

Every consumer must be safe to run twice on the same message. Two mechanisms:

1. **Dedup on a message id.** Producer stamps a stable `message_id` (or a business key). Consumer records processed ids in a store with a TTL ≥ max redelivery window; a second delivery short-circuits.
2. **Idempotent side effects.** Make the work itself naturally repeatable — `UPSERT` instead of `INSERT`, conditional update guarded by a state check, an idempotency key forwarded to the downstream API (see api-design's idempotency contract).

```python
def handle(msg: Message) -> None:
    # 1. dedup gate — INSERT ... ON CONFLICT DO NOTHING returns rowcount 0 on replay
    first_time = processed_store.claim(msg.id, ttl_seconds=DEDUP_TTL)
    if not first_time:
        msg.ack()  # already handled — ack and drop, do not reprocess
        return
    # 2. idempotent effect — guarded by business state, not just the dedup gate
    order = repo.find(msg.order_id)
    if order.status != "pending":
        msg.ack()
        return
    process(order)
    msg.ack()
```

Ack *after* the work commits, never before. Ack-before-work loses messages on a crash mid-processing.

## Retries, Backoff, and the Dead-Letter Queue

A naive immediate retry hammers a struggling downstream and reorders the stream. The contract:

- **Exponential backoff with jitter** between retries — `base * 2^attempt + random_jitter`, capped. Never a tight retry loop.
- **A retry ceiling** (commonly 3–5). After it, route to a **dead-letter queue (DLQ)**, do not retry forever — an unprocessable "poison" message blocks the partition behind it otherwise.
- **The DLQ is monitored, not a graveyard.** Alert on DLQ depth > 0; messages land there because of a bug or a bad payload, both of which need a human.
- **Separate transient from permanent failures.** A 503 from downstream → retry. A schema-invalid payload → DLQ immediately; retrying a malformed message just wastes the ceiling.

## Ordering — Only Within a Partition

Global ordering across a topic does not scale. Order is guaranteed only within one partition/queue/key.

- Pick a **partition key** that groups the events that must stay ordered (e.g. `order_id`) — all events for one order land on one partition, ordered; events for different orders interleave freely and scale out.
- More partitions = more parallelism but weaker cross-key ordering and rebalancing churn. Size for throughput, not "just in case".
- If strict total order is genuinely required, that is a single-partition (single-consumer) bottleneck — question whether the requirement is real.

## The Transactional Outbox — Don't Dual-Write

Writing to the database *and* publishing to the broker in the same handler is a dual-write: one can succeed and the other fail, leaving DB and stream inconsistent. The fix is the **outbox pattern**:

1. In the same DB transaction as the business write, insert the event into an `outbox` table. One atomic commit — no partial state.
2. A separate relay (polling or change-data-capture) reads the outbox and publishes to the broker, marking rows sent.
3. The relay is at-least-once → consumers are already idempotent → safe.

This trades "publish might be slightly delayed" for "DB and stream never disagree", which is almost always the right trade.

## Backpressure and Consumer Lag

- **Bound the prefetch / in-flight count.** Unbounded prefetch pulls the whole queue into one slow consumer's memory and starves siblings. Set a prefetch window sized to the work, not to "max".
- **Watch consumer lag** (Kafka: offset behind head; queues: depth + oldest-message age). Lag growing monotonically = consumers can't keep up → scale out or shed load, do not silently fall behind until disk fills.
- **Lag is a golden saturation signal** — wire it into the observability dashboard (see the observability skill's saturation metric).

## Anti-Patterns (reject in review, fix on sight)

- **Treating at-least-once as exactly-once** — assuming a message arrives once and skipping the idempotency gate. It will arrive twice eventually.
- **Acking before the work commits** — loses messages on crash.
- **No DLQ / infinite retry** — one poison message stalls the whole partition.
- **Tight retry loop with no backoff** — a thundering herd that takes the recovering downstream back down.
- **Dual-writing DB + broker** in one handler — use the outbox pattern.
- **Using a message broker as a database** — querying a Kafka topic for current state instead of materializing a read model.
- **Unbounded prefetch** — one consumer OOMs holding the whole backlog.
- **Ignoring DLQ depth / consumer lag** — the two signals that tell you the pipeline is broken before users do.
- **Ordering assumed across partitions** — only intra-partition order is guaranteed.

## Tools per surface (2026 defaults)

| Need | Default | Alternatives |
|---|---|---|
| Work queue (jobs) | SQS, RabbitMQ | Redis Streams, Beanstalkd |
| Event log / streaming | Kafka | Redpanda, AWS Kinesis, Pulsar |
| Lightweight pub/sub | NATS | Redis pub/sub, Google Pub/Sub |
| In-process / single-node async | language queue + worker pool | — |
| Schema registry (event contracts) | Confluent Schema Registry, Avro/Protobuf | JSON Schema + CI contract test |

## Pairs With

- **api-design** — the synchronous request/response side of the seam; this skill owns what happens after the request returns. Idempotency keys cross the boundary.
- **observability** — consumer lag and DLQ depth are saturation/error golden signals; trace context must propagate through the broker (inject `traceparent` into message headers).
- **grpc-microservices** — synchronous binary east-west RPC; choose RPC for request/reply, a queue for fire-and-forget.
- **realtime-websockets** — delivering broker events to a live client connection (fan-out via Redis/NATS pub/sub).
- **clean-code** — fail-closed handlers, typed exceptions distinguishing transient (retry) from permanent (DLQ).

## See also

- *Designing Data-Intensive Applications* (Kleppmann) ch. 11 — streams, logs, delivery guarantees.
- *Enterprise Integration Patterns* (Hohpe & Woolf) — the canonical messaging-pattern catalog.
- Kafka docs — exactly-once semantics (EOS) scope and limits.
- microservices.io — transactional outbox + saga patterns.
