<!-- domain:BACKEND | layer:reference | ssot:true | updated:2026-06-04 -->
# Instrumentation — Logs, Metrics, Traces

> P: Instrument a service so a production problem is diagnosable from telemetry, not guesswork.
> R: Adding logging/metrics/tracing to a service or debugging a blind spot.
> S: Alert routing to a runbook — that's [incident-response](../../incident-response/SKILL.md).
> N: [SKILL.md](../SKILL.md), [observability-checklist.md](../assets/observability-checklist.md)

> Nav: [Skill](../SKILL.md)

## The three signals (use all, for different questions)

| Signal | Answers | Shape |
|---|---|---|
| logs | "what exactly happened in this request?" | structured events (JSON), correlated by trace id |
| metrics | "how is the system behaving over time?" | numeric time series (counters, gauges, histograms) |
| traces | "where did the latency / error come from across services?" | spans with parent/child, a trace id end to end |

OpenTelemetry is the vendor-neutral standard for all three — instrument once,
export to Prometheus/Grafana/Datadog/etc. Don't reinvent per-vendor SDKs.

## Structured logs, never print

```python
# Wrong — unsearchable, unparseable, eager-formatted
print(f"user {user_id} did {action}")

# Correct — structured, level-gated, correlatable
logger.info("user_action", extra={"user_id": user_id, "action": action, "trace_id": trace_id})
```

Pass fields as data, not interpolated into the message — so you can filter/aggregate
on `user_id` later. Include the `trace_id` on every log so logs join to traces.
`lint_logging.py` flags `print`/`console.log`, f-strings in log calls (eager
format), and PII-shaped values.

## Metrics that matter — RED + USE

- **RED** (request-driven services): **R**ate, **E**rrors, **D**uration (p50/p95/p99).
- **USE** (resources): **U**tilization, **S**aturation, **E**rrors.

Histograms (not averages) for latency — an average hides the p99 that users feel.
Keep label cardinality low (no user-id labels — that explodes the series count).

## SLO/SLI — define "good enough" before alerting

An SLI is a measured ratio (successful requests / total); an SLO is the target
(99.9% over 30 days); the error budget is what's left. Alert on **burn rate**
(spending the budget too fast), not on every blip — page-worthy means
user-impacting, not "CPU touched 80% once".

## Alert hygiene

Every alert links to a runbook ([incident-response](../../incident-response/SKILL.md)),
is actionable (a human can do something), and is symptom-based (alert on "checkout
error rate up", not "pod restarted"). A noisy channel trains people to ignore it —
delete or tune alerts no one acts on.
