<!-- domain:FRONTEND | layer:reference | ssot:true | updated:2026-06-04 -->
# Playwright — Locators, Fixtures, Network, Traces

> P: Write reliable web end-to-end tests with auto-waiting locators and isolated state.
> R: Authoring or debugging a Playwright test.
> S: Mobile flows — see [maestro.md](maestro.md). Test-type choice — [testing-strategy](../../testing-strategy/SKILL.md).
> N: [SKILL.md](../SKILL.md), [e2e-checklist.md](../assets/e2e-checklist.md)

> Nav: [Skill](../SKILL.md)

## Locator priority (most → least reliable)

```typescript
page.getByRole("button", { name: "Submit" })   // 1. role + accessible name (best)
page.getByLabel("Email")                          // 2. form labels
page.getByText("Welcome back")                    // 3. visible text
page.getByTestId("checkout-cta")                  // 4. explicit data-testid (when no semantic anchor)
page.locator("button.btn")                        // 5. CSS — last resort, brittle
```

Role/label/text locators also verify accessibility (a missing accessible name
fails the test) — they couple correctness and a11y. Reserve `getByTestId` for
elements with no semantic anchor; never select on generated CSS classes.

## Auto-wait + web-first assertions

```typescript
await page.getByRole("button", { name: "Save" }).click();   // waits until actionable
await expect(page.getByText("Saved")).toBeVisible();          // retries up to the timeout
await expect(page).toHaveURL(/dashboard/);
```

Every action auto-waits for the element to be visible, stable, and enabled;
`expect(locator)` retries until the condition holds. This is why
`waitForTimeout` is never needed — the framework already waits for the *right*
condition instead of a guessed duration.

## Isolation via fixtures

```typescript
test.beforeEach(async ({ page }) => { await seedUser(); });
test.afterEach(async () => { await cleanupUser(); });
```

Each test gets a fresh browser context (cookies/storage isolated) by default.
Seed the data the test needs and tear it down — never rely on data a prior test
created. Use `storageState` to skip login UI by injecting an authenticated
session once.

## Mock the boundary

```typescript
await page.route("**/api/payments", (route) =>
  route.fulfill({ json: { status: "ok" } }));
```

Route third-party/flaky endpoints so the test controls the response — an
end-to-end test of *your* app shouldn't fail because Stripe's sandbox is slow.
Control time with `page.clock` for timeout/animation logic.

## Debug + CI

- `trace: "on-first-retry"` in config → a full DOM/network/console timeline on
  failure; open with `npx playwright show-trace`. Debugging CI flake without it
  is guesswork.
- Parallelize with `fullyParallel: true` + `--workers`; shard across CI machines
  with `--shard=1/4`. `retries: 1` for genuine blips only — not to mask flake.
- Browsers: `npx playwright install --with-deps` in CI; pin the Playwright version.
