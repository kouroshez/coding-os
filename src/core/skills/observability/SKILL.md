---
name: observability
tier: cross-cutting
domain: [infra]
description: Production observability done right — structured logs, distributed traces, metrics, alerting, SLO/SLI. Use when adding logging to a new service, designing dashboards, choosing between OpenTelemetry / Datadog / Grafana stack, defining SLOs for a feature, writing alert rules, or untangling a noisy alert channel. Stack-agnostic; recipes target OpenTelemetry as the canonical instrumentation, Prometheus + Grafana / Datadog as the canonical backends. Pairs with performance (perf budgets), security-web (audit logs), and incident-response (alert → runbook).
last_reviewed: "2026-05-11"
---

# Observability — Logs, Traces, Metrics, SLOs

A practical playbook for instrumenting production code so an incident at 03:00 takes minutes, not hours. Aligned with OpenTelemetry 1.x (the 2026 industry standard) and the SRE workbook's golden-signal approach.

## When to Use This Skill

- Adding logging / tracing / metrics to a new service.
- Designing dashboards before launch — observability built in, not bolted on.
- Choosing between OpenTelemetry, Datadog APM, Honeycomb, Grafana Stack, Sentry.
- Defining SLO / SLI / error-budget policy for a feature.
- Writing or reviewing alert rules — a good alert wakes a human at 03:00 for the right reason.
- Investigating "we have logs but can't find the bug" or "alerts fire constantly so nobody reads them."

Skip when: writing a one-off script or a dev-only tool with no production lifetime.

## The Three Pillars + One

Industry consensus (2020s onward) is *three pillars + traces-as-glue*:

| Pillar | Question it answers | Tools |
|---|---|---|
| **Metrics** | "How is the system doing right now?" — counters, gauges, histograms | Prometheus, Datadog Metrics, CloudWatch Metrics |
| **Logs** | "What exactly happened for *this* request?" — structured events | Loki, ELK, Datadog Logs, CloudWatch Logs |
| **Traces** | "How did the work flow across services?" — spans + parent-child links | Jaeger, Tempo, Datadog APM, Honeycomb |
| **Profiles** *(emerging fourth)* | "Why is the CPU/memory burning?" — continuous profiling | Pyroscope, Parca, Datadog Profiler |

**Always use OpenTelemetry (OTel) as the instrumentation layer.** Send to whatever backend you pick. This decouples vendor choice from code — switching from Datadog to Honeycomb becomes a config change, not a rewrite. OTel SDK is stable for traces, metrics, and logs in 2026 across Python, TypeScript, Go, Java.

## Golden Signals (Google SRE Book)

Every service has four metrics worth tracking, no matter what it does:

| Signal | What | Why |
|---|---|---|
| **Latency** | P50 / P95 / P99 of successful responses | Slow → users churn |
| **Traffic** | Requests per second / events per second | Capacity planning, anomaly baseline |
| **Errors** | Rate of failed requests (5xx for HTTP) | Reliability bottom line |
| **Saturation** | "How full" — CPU%, mem%, queue depth, connection pool used | Predicts incidents before they fire |

Dashboard rule: every service's home dashboard shows these four, large, top-left. Everything else is detail.

## Structured Logs — Rules

```python
# Good — structured, machine-parseable, no PII
logger.info("payment.captured", extra={
    "user_id": str(user.id),  # uuid, not email
    "order_id": str(order.id),
    "amount_cents": amount_cents,
    "currency": currency,
    "processor": "stripe",
    "latency_ms": int(elapsed * 1000),
})
```

```typescript
// Good — TypeScript, pino / Winston
logger.info({
  event: "payment.captured",
  user_id: user.id,
  order_id: order.id,
  amount_cents: amountCents,
  currency,
  processor: "stripe",
  latency_ms: Math.round(elapsed * 1000),
});
```

```go
// Good — Go, slog (stdlib 1.21+)
slog.Info("payment.captured",
    "user_id", user.ID,
    "order_id", order.ID,
    "amount_cents", amountCents,
    "currency", currency,
    "processor", "stripe",
    "latency_ms", elapsedMs,
)
```

**Hard rules:**

- **Structured (JSON), not prose.** Prose logs are unparseable. Even if your dev tail looks at them, prod queries need fields.
- **One event per log line.** Don't pack three things into one log call.
- **`event` field with a dotted name.** `payment.captured`, `user.signup.failed`. Stable across versions, queryable across services.
- **No PII.** No email, phone, IP, full name, full card number. Use IDs / hashed IDs. See [clean-code](../clean-code/SKILL.md) §1b.
- **No secrets, ever.** No tokens, passwords, API keys, even masked.
- **Log levels mean something.** `DEBUG` = dev only. `INFO` = a thing happened. `WARN` = unexpected but recoverable. `ERROR` = a request failed. `CRITICAL` = service degraded.
- **Trace ID in every log.** OTel correlation: every log carries `trace_id` + `span_id` so you can pivot from "this slow request" to "all logs for this request".

### Anti-patterns

- `logger.info(f"user {email} logged in")` — PII leak.
- `logger.info("done")` — no event, no context, useless.
- `logger.error("error: " + str(exc))` — `str(exc)` may leak SQL/paths; use `exc_info=True` for structured stack trace.
- Logging in a hot loop without sampling — kills your log bill.

## Distributed Traces

A trace is the request's life across services. Each step is a *span*. Parent-child spans build a tree.

```python
# Python — OpenTelemetry SDK
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

def process_order(order_id: str) -> Order:
    with tracer.start_as_current_span("process_order") as span:
        span.set_attribute("order.id", order_id)

        with tracer.start_as_current_span("db.fetch_order"):
            order = repo.find(order_id)

        with tracer.start_as_current_span("payment.capture"):
            capture_result = payment_service.capture(order)
            span.set_attribute("payment.processor", capture_result.processor)

        if capture_result.failed:
            span.set_status(trace.Status(trace.StatusCode.ERROR, "capture failed"))
            raise PaymentFailedError(capture_result.reason)

        return order
```

**Rules:**

- Every external call is a span (DB, HTTP, queue publish, third-party API).
- Span name = action, not URL. `db.fetch_order`, not `SELECT * FROM orders WHERE id=...`.
- Attributes on spans should be high-cardinality OK (`order.id`, `user.id`). Metrics shouldn't be.
- Propagate trace context across service boundaries (`traceparent` HTTP header).
- Sample tail-based in production. 100% sampling = 100% bandwidth bill.

## Metrics — the four-cardinality rule

A metric with high cardinality (= many unique label combinations) costs orders of magnitude more than a metric with low cardinality. Rule of thumb:

| Label | OK as metric label? | Why |
|---|---|---|
| `service` | ✅ | Few values, stable |
| `endpoint` (route template) | ✅ | Few values |
| `status_code` | ✅ | ~10 values |
| `region` | ✅ | Few values |
| `user_id` | ❌ | Unbounded — millions of series |
| `order_id` | ❌ | Unbounded |
| Free-text error message | ❌ | Unbounded |

Per-user data goes on traces and logs (where cardinality is fine), not metrics.

### Histograms over averages

`avg(latency)` hides the long tail. Use a histogram and query P50 / P95 / P99:

```python
# OpenTelemetry metric
from opentelemetry.metrics import get_meter

meter = get_meter(__name__)
request_duration = meter.create_histogram(
    "http.server.duration",
    unit="ms",
    description="HTTP server request duration",
)

# In the handler
start = time.perf_counter()
try:
    response = handle(req)
    request_duration.record((time.perf_counter() - start) * 1000,
                            {"method": req.method, "route": req.route, "status": response.status})
    return response
```

## SLO / SLI / Error Budget

The **SLI** (Service Level Indicator) is what you measure: `% of requests under 200ms` or `% of requests not 5xx`.

The **SLO** (Service Level Objective) is the target: `99.9% of requests under 200ms over 30 days`.

The **error budget** is what you can spend: `0.1% × 30 days × 24h = 43.2 minutes of downtime`.

### Why this matters

When the team has burned 80% of the error budget halfway through the month, **all feature work stops** and reliability work takes priority. This is the contract that prevents "always-100%-uptime" arguments from blocking ship-fast culture, and "always-ship-fast" arguments from blocking reliability work.

Concrete SLOs for typical surfaces:

| Surface | SLO suggestion |
|---|---|
| HTTP API for paying users | 99.9% availability, P95 < 300ms |
| Internal admin tool | 99% availability, P95 < 1s |
| Background job processor | 99.5% job-completion within target deadline |
| Public website | 99.9% availability, LCP < 2.5s (P75 mobile) |

## Alerting — the 03:00 rule

A page (someone-wakes-up alert) is justified only if **a) something is on fire** and **b) human action is required**. Everything else is a ticket, not a page.

### Good alerts

- "Error rate > 5% for 5 minutes on the checkout API" — users can't pay, wake up engineer.
- "Database connection pool > 90% saturated for 10 minutes" — saturation predicts outage.
- "Job queue depth > 10K and growing" — backlog forming.

### Bad alerts (delete on sight)

- "CPU > 80% for 1 minute" — CPU is supposed to be high under load.
- "Disk usage > 70%" — nothing breaks at 70%, the alert at 90% is the real one.
- "Service X restarted" — restarts are normal in K8s.
- "P99 latency spiked once" — flaps; use multi-window burn-rate alerts.

### Burn-rate alerts (Google SRE pattern)

Instead of "5xx > 1%" (fires every minute on transient blips), alert when the error budget is burning fast enough that you'll exhaust it before the SLO window ends. Catches both short outages and slow degradations.

## Audit Logs (compliance-grade)

Distinct from operational logs. Audit logs answer "who did what to which object when, and from where?":

```python
audit.record(
    actor=current_user.id,
    actor_role=current_user.role,
    action="user.permissions.granted",
    target_object=("user", target_user.id),
    target_change={"role_added": "admin"},
    request_id=request.id,
    source_ip=hash_ip(request.client_ip),  # hash for PII compliance
    timestamp_utc=now_utc(),
)
```

Audit logs go to **write-only, retention-policied storage** (separate index, separate retention from regular logs). Compliance frameworks (SOC2, GDPR, HIPAA, PCI-DSS) need them tamper-evident.

For the coding-os meta-repo specifically: see `cos_audit_log_record` / `cos_audit_log_query` MCP tools — every governance action records there.

## CI Signal Hygiene

A green build with broken observability is a lying build. Check in CI:

- **Schema lint** for log events — every `logger.info()` must include `event=` field.
- **Trace integrity** — at least one integration test asserts `trace_id` propagates from inbound HTTP → downstream HTTP / DB call.
- **No-PII linter** — grep for `email`, `phone`, `password`, raw IPs in log statements (allow only on a documented allowlist).
- **No bare `time.sleep`** in production code paths — masks real timing issues.

## Anti-patterns (reject in review)

- **Prose logs in production** — `logger.info("user logged in")`. Use structured events.
- **PII in logs** — emails, full names, IPs in cleartext.
- **`print` in production** — `print()` doesn't go through the logging pipeline; logs vanish.
- **High-cardinality metric labels** — `user_id`, `order_id` as metric labels kills your TSDB bill.
- **Averages instead of percentiles** — `avg(latency)` lies. Use histograms.
- **Alert on every error** — pages a human for noise; teaches them to mute.
- **Logs without trace_id** — can't correlate logs to traces, debugging takes 10× longer.
- **`exc.message` in logs** — may contain SQL/paths/secrets. Use `exc_info=True` for structured trace.

## Tools per surface (2026 defaults)

| Need | Open-source | Hosted |
|---|---|---|
| Instrumentation | OpenTelemetry SDK | OpenTelemetry SDK (same) |
| Metrics | Prometheus + Grafana | Datadog Metrics, Grafana Cloud |
| Logs | Loki + Grafana, or ELK | Datadog Logs, Splunk |
| Traces | Tempo + Grafana, Jaeger | Datadog APM, Honeycomb |
| Errors / Exceptions | Sentry (self-hosted) | Sentry SaaS |
| Profiling | Pyroscope (Grafana) | Datadog Profiler |
| Alerts | Alertmanager (Prometheus) | PagerDuty, OpsGenie |

## See also

- [performance](../performance/SKILL.md) — pairs naturally with metrics + traces.
- [security-web](../security-web/SKILL.md) §A09 (Logging & Alerting Failures) — security-side audit log requirements.
- [incident-response](../incident-response/SKILL.md) — when alerts fire, what happens next.
- [clean-code](../clean-code/SKILL.md) §1b — no PII in logs.
