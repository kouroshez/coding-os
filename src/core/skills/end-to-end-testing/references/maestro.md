<!-- domain:MOBILE | layer:reference | ssot:true | updated:2026-06-04 -->
# Maestro — Mobile End-to-End Flows

> P: Drive real iOS/Android user journeys with declarative, retry-built-in flows.
> R: Authoring or debugging a mobile end-to-end test.
> S: Web tests — see [playwright.md](playwright.md).
> N: [SKILL.md](../SKILL.md), [e2e-checklist.md](../assets/e2e-checklist.md)

> Nav: [Skill](../SKILL.md)

## A flow is declarative YAML

```yaml
# flows/checkout.yaml
appId: com.example.app
---
- launchApp:
    clearState: true            # isolation: start from a known state
- tapOn: "Add to cart"
- tapOn:
    id: "checkout_button"       # prefer accessibility id over visible text when ambiguous
- assertVisible: "Order confirmed"
```

Each step waits for the UI implicitly — Maestro retries `tapOn`/`assertVisible`
until the element appears or it times out. No manual sleeps. `clearState: true`
gives test isolation (fresh app data per flow).

## Select by accessibility, not pixels

```yaml
- tapOn: "Sign in"            # visible text
- tapOn:
    id: "email_field"         # accessibilityIdentifier / resource-id (most stable)
- inputText: "user@example.com"
```

Use text or the platform accessibility id (`accessibilityIdentifier` on iOS,
`resource-id`/`contentDescription` on Android). Never tap by coordinates — it
breaks on any layout or device change. Accessible labels make the app testable
*and* usable (see [a11y](../../a11y/SKILL.md)).

## Reuse + parameterize

```yaml
# login.yaml as a subflow
- runFlow: login.yaml
- runFlow:
    file: checkout.yaml
    env: { PRODUCT: "Book" }
```

Extract shared steps (login) into subflows; pass `env` to parameterize. Keep each
flow one journey — a 60-step mega-flow is hard to debug when step 47 fails.

## CI + debugging

- `maestro test flows/` runs the suite; `maestro cloud` runs across a device
  matrix. Record with `maestro record` to get a video of a failure.
- Run against emulators/simulators in CI; pin the Maestro CLI version
  ([versions.json](../versions.json)).
- Built-in retry handles real UI timing — don't add sleeps. If a flow is flaky,
  the selector is ambiguous or the app has a real race; fix the root cause.
