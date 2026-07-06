---
name: testing-strategy
tier: quality
domain: [universal]
description: Choose the right test type for every change — unit, integration, contract, end-to-end, property-based, mutation, fuzz. Use when adding tests to a new feature, deciding what to test for a bug fix, designing a test pyramid for a service, evaluating coverage targets, or untangling a slow test suite. Stack-agnostic; concrete recipes target Python (pytest), TypeScript (Vitest/Jest/Playwright), and Go (table tests + testify). Pairs with clean-code (error-path tests) and observability (CI signal hygiene).
last_reviewed: "2026-05-11"
---

# Testing Strategy — Pick the Right Layer

A practical playbook for designing test suites that catch real bugs without the suite itself becoming the bug. Stack-agnostic core; concrete recipes target this project's languages.

## When to Use This Skill

- Adding the first test to a new module — the shape you ship now sets the suite's trajectory.
- Reviewing a PR where the test ratio looks off (e.g. all unit, no contract; all e2e, no unit).
- Investigating a flaky / slow suite — the cure is almost never "add retries".
- Deciding coverage targets for a service (90% lines is the wrong target).
- Adding tests to a bug fix — the fix without a regression test will return.
- Migrating from manual QA → automated CI.

Skip when: writing throwaway exploration code. Real code, real tests.

## The Test Pyramid (still right, refined for 2026)

```
                ┌─────────┐
                │   E2E   │  ~5%   slow,    flake-prone, golden-path
            ┌───┴─────────┴───┐
            │   Contract +    │  ~15%  pact, OpenAPI, GraphQL schema
            │   Integration   │
        ┌───┴─────────────────┴───┐
        │                          │
        │      Unit + Property     │  ~80%  fast (ms), deterministic
        │                          │
        └──────────────────────────┘
```

Targets are guidance, not law. A library has more unit + property than a deployment-heavy SaaS. A regulated app has more contract + integration than a hackathon prototype. **What stays constant: most tests are fast; few tests are slow; zero tests are flaky.**

## The Six Layers — When Each Pays Off

| Layer | Speed | Catches | Use For |
|---|---|---|---|
| **Unit** | <10ms | Logic bugs, edge cases | Pure functions, calculators, parsers, mappers |
| **Property-based** | <100ms | Bugs you didn't think of | Invariants, parsers, encoders, ordering rules |
| **Integration** | <1s | Wiring bugs | DB queries (real DB, not mock), service composition |
| **Contract** | <100ms | Producer/consumer drift | API schemas, MCP envelope, event payloads |
| **E2E** | 5–60s | Full-stack regressions | One golden path per critical user flow |
| **Smoke / run-the-deliverable** | seconds | Import/entry crashes the unit suite hides (e.g. `ModuleNotFoundError` when run as a file) | Every new runnable entrypoint — `--help` / `--dry-run` / `python -c "import x"`, from the same entry the user or cron uses |
| **Mutation / Fuzz** | minutes (offline) | Tests that don't actually test | Quarterly audit, security-critical code |

### Unit tests — the workhorse

A unit test executes one function in isolation. **No I/O, no clock, no network, no shared state.** Sub-10ms each so you can run 10K of them in CI.

```python
# Python — pytest
def test_calculate_discounted_price_applies_percentage() -> None:
    result = calculate_discounted_price(Decimal("100"), Decimal("20"))
    assert result == Decimal("80")

def test_calculate_discounted_price_rejects_negative_discount() -> None:
    with pytest.raises(InvalidDiscountError, match="negative"):
        calculate_discounted_price(Decimal("100"), Decimal("-5"))
```

```typescript
// TypeScript — Vitest
describe("calculateDiscountedPrice", () => {
  it("applies percentage to base price", () => {
    expect(calculateDiscountedPrice(100, 20)).toBe(80);
  });

  it("rejects negative discount", () => {
    expect(() => calculateDiscountedPrice(100, -5))
      .toThrow(/negative/);
  });
});
```

**Anti-pattern:** mocking five frameworks to test one calculation. If you need five mocks for a unit test, the function isn't a unit. Extract the pure logic.

### Property-based tests — bugs you didn't think of

Instead of asserting `f(2) == 4`, you assert an *invariant* (`f(x) >= 0 for any x >= 0`) and let the framework generate hundreds of inputs to try and break it.

```python
# Python — Hypothesis
from hypothesis import given, strategies as st

@given(price=st.decimals(min_value=0, max_value=10_000), pct=st.decimals(min_value=0, max_value=100))
def test_discount_never_negative(price: Decimal, pct: Decimal) -> None:
    result = calculate_discounted_price(price, pct)
    assert result >= 0
    assert result <= price
```

```typescript
// TypeScript — fast-check
import fc from "fast-check";

test("discount never produces negative or > base", () => {
  fc.assert(
    fc.property(fc.float({min: 0, max: 10000}), fc.float({min: 0, max: 100}),
      (price, pct) => {
        const r = calculateDiscountedPrice(price, pct);
        return r >= 0 && r <= price;
      }
    )
  );
});
```

Use for: parsers, encoders, comparison/ordering, anything with mathematical invariants, anywhere "off-by-one" is a real risk.

### Integration tests — the wiring layer

Real DB (testcontainers / pytest-postgresql / sqlite-in-memory for sqlite-targeted code), real HTTP, real serialization. Mock only third-party HTTP services (and use a recorded-cassette tool like `vcrpy` / `nock` so the mock is honest).

**Rule:** the integration test goes through the same code path production does. If production hits PostgreSQL, the test hits PostgreSQL — not SQLite, not a mock. Mock/prod divergence is the #1 source of "tests pass, prod breaks."

```python
# Python — pytest with testcontainers
@pytest.fixture
def db():
    with PostgresContainer("postgres:16") as pg:
        engine = create_engine(pg.get_connection_url())
        Base.metadata.create_all(engine)
        yield engine

def test_user_repository_finds_by_email(db) -> None:
    with Session(db) as session:
        session.add(User(email="a@b.com", name="A"))
        session.commit()

        repo = UserRepository(session)
        user = repo.find_by_email("a@b.com")

        assert user is not None
        assert user.name == "A"
```

### Contract tests — the seam between services

When team A produces and team B consumes, **what you both agree on is the contract**, not your respective unit tests. Contract tests verify the schema (OpenAPI / GraphQL / event-payload / MCP envelope) is what both sides expect.

For the coding-os meta-repo specifically: every `cos_*` MCP tool MUST return the envelope from [docs/engineering/mcp-error-envelope.md](../../../docs/engineering/mcp-error-envelope.md) — `ok(data)` or `fail(category, message)`. The contract test asserts this shape against the live tool output.

```python
# Contract test pattern — meta-repo MCP
def test_cos_search_returns_envelope() -> None:
    result = invoke_tool("cos_search", {"query": "test"})
    assert "ok" in result
    if result["ok"]:
        assert "data" in result
        assert "meta" in result["data"]
    else:
        assert "error" in result
        assert "category" in result["error"]
```

For HTTP services: use `schemathesis` (Python) or `dredd` to drive tests directly from the OpenAPI spec. The spec IS the test.

### E2E tests — one per golden path

End-to-end through a real browser (Playwright) / real mobile device (Detox / Maestro) / real API (curl-style integration). They are slow and flaky, so **keep them few and intentional**.

Rule of thumb: one E2E per user-facing outcome that, if broken, would generate a support ticket within an hour. Typical SaaS: 5–15 E2E tests total.

```typescript
// Playwright — golden path
test("user can sign up, verify email, and reach dashboard", async ({page}) => {
  await page.goto("/signup");
  await page.fill('[name="email"]', `test-${Date.now()}@example.com`);
  await page.fill('[name="password"]', "ValidPassword123!");
  await page.click('button[type="submit"]');

  // Don't poll forever — fail loud at 10s
  await expect(page).toHaveURL(/dashboard/, {timeout: 10_000});
});
```

### Mutation testing — the test of tests

Mutation testing changes one operator at a time in your production code (`+` → `-`, `>` → `>=`) and re-runs your tests. If your tests still pass, that mutation is "alive" — your tests don't actually exercise that code. Run quarterly, not in CI.

- Python: `mutmut`, `cosmic-ray`
- TypeScript / JS: `stryker`
- Go: `go-mutesting`

For security-critical code (auth, payment, crypto), aim for ≥85% mutation score. For other code, ≥60% is good signal.

## Three Rules of Test Authorship

1. **Test the behavior, not the implementation.** A test that calls a private method or mocks an internal class breaks every refactor. Test the public API surface — what callers see.
2. **One assertion idea per test.** A test asserting six unrelated things fails opaquely. Split into six tests with clear names.
3. **Name the failure, not the success.** `test_returns_404_when_user_not_found` beats `test_get_user`. The failing test message should already tell you what broke.

## The Error-Path Contract

Every `try/except` (Python) / `try/catch` (TypeScript) / `if err != nil` (Go) block needs a test that triggers the error branch. This is the [clean-code](../clean-code/SKILL.md) contract. Repeating it here because most suites get this wrong:

```python
def test_verify_purchase_raises_on_verification_failure(mocker) -> None:
    mocker.patch("apps.purchases.services.PurchaseService.get_verified",
                 side_effect=VerificationError("upstream timeout"))

    with pytest.raises(ServiceUnavailableError, match="Unable to verify"):
        verify_purchase("user-1", "product-1")
```

## Coverage — the right target

**Line coverage ≥ 80%** is a useful floor, not a goal. Bad code with 100% line coverage and no edge-case tests is worse than good code with 75% line coverage and complete branch + error-path tests.

What to actually measure:

| Metric | Target | Why |
|---|---|---|
| Line coverage | ≥ 80% | Useful floor, easy to game |
| Branch coverage | ≥ 70% | Catches missed `else` / `case` arms |
| **Mutation score** | ≥ 60% (≥85% for crypto/auth/payments) | The honest number |
| **Error-path coverage** | 100% of `except`/`catch`/`if err` | Non-negotiable for prod code |

## Test Hygiene — the rules that prevent suite rot

- **Test independence.** Every test sets up its own state and tears it down. Order-dependent tests are bugs.
- **No shared mutable globals.** Use fixtures with explicit scope.
- **Deterministic clock + IDs.** Inject `time.now` / use `freezegun`. UUID generators with seeded RNG.
- **No `time.sleep`.** Use polling with timeout, not blind sleeps. Replace `sleep(0.1)` with `wait_for(condition, timeout=2)`.
- **Flake budget = 0.** A "sometimes-failing" test is broken. Quarantine and fix or delete.
- **Fast = under 100ms per unit, under 1s per integration, under 10s per E2E.** If slower, investigate before merging.
- **Hermetic CI.** Test container's network egress disabled where possible. No reaching out to a real Stripe sandbox in CI.

## Anti-patterns (reject in review)

- **Mocking what you don't own** — mocking a third-party SDK at the call boundary is fine; mocking `requests.get` in 40 tests means you're testing the mock library.
- **`assert True` / `assert not None`** — assert the actual value.
- **`try: ... except: pass` in test code** — swallowing an exception in a test hides bugs in the test code itself.
- **Sleep-based wait** — replace with explicit poll.
- **Snapshot tests for everything** — snapshot tests on dynamic output (timestamps, UUIDs) generate noise. Use them for stable HTML/JSON only.
- **Testing the framework** — don't write tests for `pydantic.BaseModel` accepting a string. Test your code.
- **One giant `test_main` function** — split.

## Verification (meta-repo specific)

This skill's own examples should pass in coding-os. Verify:

- `uv run --extra rag pytest src/core/thinking_os/tests/ -q` — matrix command for thinking_os.
- `uv run pytest tests/test_skill_frontmatter.py -q` — this skill's frontmatter is valid.

## Tooling

Gate coverage in CI (coverage.py JSON or Cobertura XML):
`python3 scripts/coverage_gate.py coverage.json --min 80`

## See also

- [references/test-types.md](references/test-types.md) — when each test type pays off + the pyramid.
- [assets/test-review-checklist.md](assets/test-review-checklist.md) — the review gate.
- [clean-code](../clean-code/SKILL.md) — error-path test contract.
- [observability](../observability/SKILL.md) — CI signal hygiene (don't trust a green run with broken telemetry).
- [search](../search/SKILL.md) — finding existing tests before adding new ones.
- [api-design](../api-design/SKILL.md) — contract test seam.
- [src/core/rules/test-discipline.md](../../rules/test-discipline.md) — matrix-targeted test command discipline for this repo.
