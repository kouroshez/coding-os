<!-- domain:BACKEND | layer:asset | ssot:false | updated:2026-06-04 -->
# Backend Review Checklist

Run when writing or reviewing server-side code.

## Layering
- [ ] Handler is thin: parse/validate → call service → format response.
- [ ] Service holds the business rules, framework-free (no HTTP/request objects).
- [ ] Repository is the only place with SQL/ORM.
- [ ] `python3 scripts/check_layering.py <service/domain files>` → `clean`.

## Correctness
- [ ] State-changing operations are idempotent (key/upsert); webhooks tolerate duplicates.
- [ ] Errors return one consistent envelope + correct status; no stack traces leaked.
- [ ] Input validated at the boundary; output shape matches the contract.

## Scale
- [ ] No N+1 (batched/joined); every list endpoint paginated.
- [ ] Queries are index-backed; assume the table grows 1000×.
- [ ] Slow/retryable work offloaded to a queue, not the request thread.

## Data
- [ ] Migrations backward-compatible (expand→contract); no drop the live code reads.
- [ ] No PII/secrets in logs (ids/redaction).

## Verify
- [ ] Matrix-targeted tests for what changed (test-discipline), error paths covered.
