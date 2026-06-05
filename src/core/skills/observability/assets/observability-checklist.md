<!-- domain:BACKEND | layer:asset | ssot:false | updated:2026-06-04 -->
# Observability Checklist

Run before shipping a service to production.

## Logs
- [ ] Structured (JSON) logger, not `print`/`console.log`.
- [ ] Fields passed as data, not interpolated into the message.
- [ ] `trace_id`/correlation id on every log (logs join to traces).
- [ ] No PII/secrets in log values (use ids; redact).
- [ ] Levels used correctly (error = actionable, info = events, debug = dev-only).
- [ ] `python3 scripts/lint_logging.py <files>` → `clean`.

## Metrics
- [ ] RED metrics for request paths (rate, errors, duration histograms).
- [ ] USE metrics for resources (utilization, saturation, errors).
- [ ] Latency as histograms (p50/p95/p99), not averages.
- [ ] Low label cardinality (no per-user/per-id labels).

## Traces
- [ ] OpenTelemetry instrumentation; trace id propagated across service calls.
- [ ] External calls (DB, HTTP) wrapped in spans.

## Alerting
- [ ] SLO/SLI defined; alerts fire on burn rate / symptoms, not every blip.
- [ ] Every alert is actionable + links to a runbook (incident-response).
- [ ] Deploy markers emitted to metrics (correlate regressions to releases).
