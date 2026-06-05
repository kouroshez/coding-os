<!-- domain:FRONTEND | layer:asset | ssot:false | updated:2026-06-04 -->
# End-to-End Test Ship Checklist

Run before adding or merging an end-to-end test.

## Scope
- [ ] Covers a critical user journey (sign-up/login, checkout, core CRUD) — not an edge case.
- [ ] Edge cases / validation / error states pushed down to unit/integration tests.
- [ ] The suite stays small enough to run on every PR.

## Reliability
- [ ] Zero `waitForTimeout`/`sleep` — auto-waiting locators + web-first `expect` (or Maestro implicit waits).
- [ ] Semantic locators (`getByRole`/`getByLabel`/text / accessibility id) — no CSS-class/nth-child/coordinate selectors.
- [ ] Each test seeds + tears down its own data; passes alone and in any order.
- [ ] Third-party/flaky endpoints mocked (Playwright `route`) — no real external calls.
- [ ] Every test has at least one assertion.
- [ ] `python3 scripts/lint_e2e.py <spec files>` → `clean`.

## CI
- [ ] Headless, parallel/sharded; `retries` ≤ 2 for real blips only.
- [ ] Trace on failure (Playwright `trace: on-first-retry` / Maestro recording).
- [ ] Browsers/devices provisioned (`playwright install`, emulators); versions pinned.
- [ ] `make skills-check-versions` — Playwright/Maestro pins current.
