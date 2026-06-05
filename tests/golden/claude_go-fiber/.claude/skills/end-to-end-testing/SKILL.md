---
name: end-to-end-testing
tier: quality
domain: [frontend, mobile]
description: Write reliable end-to-end tests that exercise real user journeys — Playwright for web, Maestro for mobile — without the flakiness that makes teams ignore them. Use when adding an end-to-end test, debugging a flaky test, choosing what to cover end-to-end vs unit/integration, setting up CI for browser/device tests, or replacing hard sleeps and brittle selectors with reliable ones. Triggers — "end-to-end test", "e2e", "Playwright", "Maestro", "the test is flaky", "browser test", "user flow test", "test the signup flow". Pairs with testing-strategy (which test type to pick — end-to-end is the top of the pyramid, used sparingly), a11y (accessible locators double as test locators), frontend-fundamentals + mobile-fundamentals.
globs: ""
paths: []
last_reviewed: "2026-06-04"
versions_ref: versions.json
---

# End-to-End Testing

End-to-end tests are the most valuable and the most expensive tests — they prove a real user journey works across the whole stack, and they break for unrelated reasons if written carelessly. The discipline: **few but critical** journeys, **semantic** locators, **zero hard sleeps**, and **isolated** data. A flaky end-to-end suite is worse than none — teams learn to ignore red.

> Lint Playwright specs for flakiness anti-patterns:
> `python3 scripts/lint_e2e.py tests/**/*.spec.ts`

## Cover journeys, not units (it's the tip of the pyramid)

End-to-end tests are slow and broad — reserve them for the handful of journeys
that, if broken, mean the product is down: sign up → log in, add to cart →
checkout, the core create→read→update path. Everything else (edge cases, error
states, validation) is cheaper and more reliable as unit/integration tests.
Which test type for a given change is owned by
[testing-strategy](../testing-strategy/SKILL.md) — this skill is how to write the
end-to-end ones well.

## Playwright — locators + auto-wait (web)

```typescript
// Wrong — brittle selector + a hard sleep = flaky and slow
await page.waitForTimeout(3000);
await page.click(".btn-primary.css-1x2y3z");      // generated class, breaks on rebuild

// Correct — semantic locator + auto-waiting assertion
await page.getByRole("button", { name: "Sign in" }).click();   // waits for actionable
await expect(page.getByText("Welcome")).toBeVisible();          // retries until true or times out
```

Playwright **auto-waits** for elements to be actionable — `getByRole`/`getByLabel`/
`getByText` plus web-first `expect` assertions retry automatically. A
`waitForTimeout` is always wrong: either too short (flaky) or too long (slow).
Prefer role/label/text locators (they double as accessibility checks — see
[a11y](../a11y/SKILL.md)) over CSS/XPath. Detail → [references/playwright.md](references/playwright.md).

## Maestro — flows for mobile

```yaml
# flows/login.yaml
appId: com.example.app
---
- launchApp
- tapOn: "Email"
- inputText: "user@example.com"
- tapOn: "Sign in"
- assertVisible: "Welcome"
```

Maestro drives real iOS/Android (or emulators) from a declarative YAML flow. It
has built-in retry/wait — no manual sleeps. Select by accessible text/id, not
pixel coordinates. Detail → [references/maestro.md](references/maestro.md).

## Kill flakiness at the source

| Flake cause | Fix |
|---|---|
| hard sleep (`waitForTimeout`) | auto-waiting locator + web-first `expect` |
| brittle selector (CSS class, nth-child) | `getByRole`/`getByTestId`/accessible text |
| shared/leftover data between tests | each test seeds + tears down its own data |
| test order dependence | full isolation — any test runs alone |
| real network to third parties | mock/route external calls; control the clock |
| race on navigation | `await` the action; let auto-wait handle readiness |

A test must pass **alone and in any order**. If it needs a previous test to have
run, it's not a test — it's a step in a script.

## CI

Run headless, sharded across workers (`--workers`, Playwright `--shard`),
retries = 1–2 for true environment blips only (not to paper over flake). On
failure, capture the **trace** (Playwright `trace: on-first-retry`) / Maestro
recording — debugging a CI-only failure without a trace is guesswork. Pin
versions ([versions.json](versions.json)); browsers via `playwright install`.

## Anti-patterns (reject on sight)

- `waitForTimeout` / `sleep` anywhere → auto-waiting assertion instead.
- CSS/XPath selectors tied to styling or generated classes → semantic locators.
- A test that depends on another test's data or order → isolate it.
- Hitting real third-party APIs in an end-to-end test → mock the boundary.
- A test with no assertion (only actions) → it proves nothing.
- Hundreds of end-to-end tests covering edge cases → push those down to unit/integration.
- Retries cranked to 5 to hide flake → fix the root cause.

## See also

- [references/playwright.md](references/playwright.md) — locators, fixtures, network mocking, traces, parallelism.
- [references/maestro.md](references/maestro.md) — flows, selectors, CI, device matrix.
- [assets/e2e-checklist.md](assets/e2e-checklist.md) — the ship gate.
- [testing-strategy](../testing-strategy/SKILL.md) · [a11y](../a11y/SKILL.md).
